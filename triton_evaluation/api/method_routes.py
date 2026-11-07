"""Caller-owned custom-method-v1 registration and durable submission."""

import asyncio
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response

from ..methods.contracts import (
    ArtifactUpload,
    MethodAlias,
    MethodAliasResponse,
    MethodExecution,
    MethodPackage,
    MethodRuntimesResponse,
    MethodSubmission,
    Name,
    RegisteredMethod,
    StoredArtifact,
)
from ..methods.registry import MethodRegistryError
from ..serialization import canonical_json_bytes
from ..service.admission import ForbiddenError
from ..service.broker import StorageError
from ..service.instance import EvaluationInstance, InstanceNotReadyError, QueueUnavailableError
from ..service.security import Caller
from . import errors
from .auth import require_read_caller, require_submit_caller
from .contract import ErrorInfo, EvaluationRequest, EvaluationResource
from .dependencies import get_instance
from .routes import TERMINAL_STATES, wait_until_terminal
from .schemas import IdempotencyKey, SessionId

router = APIRouter()
ReadCaller = Annotated[Caller, Depends(require_read_caller)]
WriteCaller = Annotated[Caller, Depends(require_submit_caller)]
Instance = Annotated[EvaluationInstance, Depends(get_instance)]


def _registry_error(error):
    return errors.ApiError(
        error.status,
        ErrorInfo(
            code=error.code,
            phase="request",
            check=None,
            retryable=False,
            message=str(error),
        ),
    )


def _same_submission(stored, submission):
    return (
        stored is not None
        and stored.method_execution is not None
        and canonical_json_bytes(stored.method_execution.submission.model_dump(mode="json"))
        == canonical_json_bytes(submission.model_dump(mode="json"))
    )


@router.post(
    "/methods",
    response_model=RegisteredMethod,
    status_code=201,
    responses=errors.error_responses(401, 403, 404, 409, 422, 500),
)
def register_method(
    package: MethodPackage,
    caller: WriteCaller,
    instance: Instance,
    expected_digest: Annotated[str | None, Header(alias="X-Expected-Digest")] = None,
):
    try:
        return instance.methods.register(caller, package, expected_digest)
    except MethodRegistryError as error:
        raise _registry_error(error) from None


@router.get(
    "/methods/{method_ref}",
    response_model=RegisteredMethod,
    responses=errors.error_responses(401, 403, 404, 500),
)
def get_method(method_ref: str, caller: ReadCaller, instance: Instance):
    try:
        return instance.methods.resolve(caller, method_ref)
    except MethodRegistryError as error:
        raise _registry_error(error) from None


@router.put(
    "/method-aliases/{alias}",
    response_model=MethodAliasResponse,
    responses=errors.error_responses(401, 403, 404, 422),
)
def put_alias(alias: Name, binding: MethodAlias, caller: WriteCaller, instance: Instance):
    try:
        return instance.methods.alias(caller, alias, binding.method_ref)
    except MethodRegistryError as error:
        raise _registry_error(error) from None


@router.post(
    "/method-artifacts",
    response_model=StoredArtifact,
    status_code=201,
    responses=errors.error_responses(401, 403, 409, 422),
)
def upload_artifact(upload: ArtifactUpload, caller: WriteCaller, instance: Instance):
    try:
        return instance.methods.upload(caller, upload)
    except MethodRegistryError as error:
        raise _registry_error(error) from None


@router.get(
    "/method-artifacts/{artifact_ref}",
    response_model=StoredArtifact,
    responses=errors.error_responses(401, 403, 404, 500),
)
def get_artifact(artifact_ref: str, caller: ReadCaller, instance: Instance):
    try:
        return instance.methods.artifact(caller, artifact_ref)
    except MethodRegistryError as error:
        raise _registry_error(error) from None


@router.get(
    "/method-runtimes",
    response_model=MethodRuntimesResponse,
    responses=errors.error_responses(401, 403),
)
def method_runtimes(caller: ReadCaller, instance: Instance):
    return instance.methods.runtimes()


@router.post(
    "/method-evaluations",
    response_model=EvaluationResource,
    responses=errors.error_responses(400, 401, 403, 404, 409, 413, 422, 429, 500, 503),
)
async def submit_method(
    submission: MethodSubmission,
    request: Request,
    response: Response,
    caller: WriteCaller,
    instance: Instance,
    session_id: Annotated[SessionId | None, Header(alias="X-Session-ID")] = None,
    idempotency_key: Annotated[IdempotencyKey | None, Header(alias="Idempotency-Key")] = None,
    wait_seconds: Annotated[int, Query(ge=0, le=60)] = 0,
):
    key = idempotency_key or uuid4().hex
    session = session_id or ("default" if idempotency_key else uuid4().hex)
    try:
        existing = await asyncio.to_thread(instance.store.lookup_idempotent, caller.caller_id, key)
        internal = None
        if existing is not None:
            stored = await asyncio.to_thread(
                instance.store.request_visible, existing.evaluation_id, caller, session
            )
            if not _same_submission(stored, submission):
                raise errors.idempotency_conflict()
            internal = stored
        if internal is None:
            execution = await asyncio.to_thread(instance.methods.freeze, caller, submission)
            internal = EvaluationRequest(
                schema_version="2.1",
                purpose="trial",
                implementation="method",
                op_name="method",
                reference_code="",
                kernel_code="",
                checks=["method"],
                deadline_seconds=submission.deadline_seconds,
                method_execution=execution,
            )
        outcome = await asyncio.to_thread(
            instance.submit, internal, caller, session_id=session, idempotency_key=key
        )
    except MethodRegistryError as error:
        raise _registry_error(error) from None
    except ForbiddenError:
        raise errors.forbidden() from None
    except InstanceNotReadyError:
        raise errors.not_ready() from None
    except QueueUnavailableError:
        raise errors.queue_unavailable() from None
    except StorageError:
        raise errors.internal() from None
    resource = outcome.resource
    if outcome.decision == "conflict":
        # Another same-key submission may have won admission after this caller
        # resolved a moving alias. Recover by the original request, not a newly
        # resolved package; never execute an accepted logical request twice.
        resource = await asyncio.to_thread(instance.store.lookup_idempotent, caller.caller_id, key)
        stored = (
            None
            if resource is None
            else await asyncio.to_thread(
                instance.store.request_visible,
                resource.evaluation_id,
                caller,
                session,
            )
        )
        if not _same_submission(stored, submission):
            raise errors.idempotency_conflict()
    if outcome.decision == "rate_limited":
        raise errors.rate_limited()
    if outcome.decision == "limit_exceeded":
        raise errors.limit_exceeded("caller inflight limit exceeded")
    if resource.state not in TERMINAL_STATES and wait_seconds:
        resource = (
            await wait_until_terminal(
                instance,
                caller,
                resource.evaluation_id,
                budget_seconds=wait_seconds,
                poll_seconds=instance.settings.api_poll_interval_seconds,
                is_disconnected=request.is_disconnected,
            )
            or resource
        )
    if resource.state not in TERMINAL_STATES:
        response.status_code = 202
        response.headers["Location"] = f"/evaluations/{resource.evaluation_id}"
    return resource


@router.post(
    "/evaluations/{evaluation_id}/cancel",
    response_model=EvaluationResource,
    responses=errors.error_responses(401, 403, 404),
)
def cancel_evaluation(
    evaluation_id: str, response: Response, caller: WriteCaller, instance: Instance
):
    resource = instance.store.cancel_visible(evaluation_id, caller)
    if resource is None:
        raise errors.not_found()
    if resource.state not in TERMINAL_STATES:
        response.status_code = 202
    return resource


@router.get(
    "/evaluations/{evaluation_id}/artifacts/{name:path}",
    response_model=StoredArtifact,
    responses=errors.error_responses(401, 403, 404),
)
def evaluation_artifact(evaluation_id: str, name: str, caller: ReadCaller, instance: Instance):
    artifact = instance.store.method_artifact_visible(evaluation_id, caller, name)
    if artifact is None:
        raise errors.not_found()
    return artifact


@router.get(
    "/evaluations/{evaluation_id}/method-materials",
    response_model=MethodExecution,
    responses=errors.error_responses(401, 403, 404),
)
def method_materials(evaluation_id: str, caller: ReadCaller, instance: Instance):
    """Recover admission-frozen bytes independently of registry object expiry."""
    request = instance.store.request_visible(evaluation_id, caller)
    if request is None or request.method_execution is None:
        raise errors.not_found()
    return request.method_execution
