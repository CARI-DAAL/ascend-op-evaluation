"""HTTP admission, waiting and recovery responses shared by evaluation routes."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from inspect import isawaitable
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header, Query, Request, Response

from ascend_op_eval.api import errors
from ascend_op_eval.api.contract import EvaluationRequest, EvaluationResource
from ascend_op_eval.api.schemas import IdempotencyKey, SessionId
from ascend_op_eval.control.admission import ForbiddenError
from ascend_op_eval.control.broker import StorageError
from ascend_op_eval.control.instance import (
    EvaluationInstance,
    InstanceNotReadyError,
    QueueUnavailableError,
)
from ascend_op_eval.control.models import CreateResourceResult
from ascend_op_eval.control.security import Caller
from ascend_op_eval.execution.correctness_evidence import CorrectnessEvidenceError

TERMINAL_STATES = ("completed", "failed", "timed_out", "cancelled")


async def wait_until_terminal(
    instance: EvaluationInstance, caller: Caller, evaluation_id: str, *,
    budget_seconds: float, poll_seconds: float,
    is_disconnected: Callable[[], bool | Awaitable[bool]],
) -> EvaluationResource | None:
    """Poll the durable resource until terminal, budget end, or disconnect.

    Waiting never terminalizes and never cancels; the caller simply receives
    the current nonterminal resource when its budget ends.
    """
    deadline = time.monotonic() + budget_seconds
    resource = await asyncio.to_thread(instance.get, evaluation_id, caller)
    while resource is not None and resource.state not in TERMINAL_STATES:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        disconnected = is_disconnected()
        if isawaitable(disconnected):
            disconnected = await disconnected
        if disconnected:
            break
        await asyncio.sleep(min(poll_seconds, remaining))
        resource = await asyncio.to_thread(instance.get, evaluation_id, caller)
    return resource


@dataclass(frozen=True)
class HttpSubmission:
    """Resolve one request's identity and wait budget before durable admission."""

    session_id: str
    idempotency_key: str
    wait_seconds: int

    async def admit(
        self, instance: EvaluationInstance, caller: Caller, internal_request: EvaluationRequest,
    ) -> CreateResourceResult:
        try:
            outcome = await asyncio.to_thread(
                instance.submit, internal_request, caller,
                session_id=self.session_id, idempotency_key=self.idempotency_key,
            )
        except ForbiddenError:
            raise errors.forbidden() from None
        except CorrectnessEvidenceError as error:
            raise errors.invalid_request_schema(str(error)) from None
        except InstanceNotReadyError:
            raise errors.not_ready() from None
        except QueueUnavailableError:
            raise errors.queue_unavailable() from None
        except StorageError:
            raise errors.internal() from None

        if outcome.decision == "rate_limited":
            raise errors.rate_limited()
        if outcome.decision == "limit_exceeded":
            raise errors.limit_exceeded("caller inflight limit exceeded")
        return outcome

    async def respond(
        self, request: Request, response: Response, instance: EvaluationInstance,
        caller: Caller, resource: EvaluationResource,
    ) -> EvaluationResource:
        if self.wait_seconds and resource.state not in TERMINAL_STATES:
            snapshot = await wait_until_terminal(
                instance, caller, resource.evaluation_id, budget_seconds=self.wait_seconds,
                poll_seconds=instance.settings.api_poll_interval_seconds,
                is_disconnected=request.is_disconnected,
            )
            if snapshot is not None:
                resource = snapshot
        if resource.state not in TERMINAL_STATES:
            response.status_code = 202
            response.headers["Location"] = request.url_for(
                "get_evaluation", evaluation_id=resource.evaluation_id,
            ).path
        return resource


async def submission_options(
    session_id: Annotated[SessionId | None, Header(alias="X-Session-ID")] = None,
    idempotency_key: Annotated[IdempotencyKey | None, Header(alias="Idempotency-Key")] = None,
    wait_seconds: Annotated[int, Query(
        ge=0, le=60,
        description="Wait for a terminal result; expiry returns 202 without cancelling work.",
    )] = 0,
) -> HttpSubmission:
    return HttpSubmission(
        session_id=session_id or ("default" if idempotency_key else uuid4().hex),
        idempotency_key=idempotency_key or uuid4().hex,
        wait_seconds=wait_seconds,
    )


Submission = Annotated[HttpSubmission, Depends(submission_options)]
