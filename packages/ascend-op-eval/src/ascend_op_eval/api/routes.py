"""Durable POST/GET evaluation endpoints.

POST admits (or replays) one durable evaluation and may wait briefly for a
terminal state; GET recovers a visible resource by ID. Once a resource
exists, execution errors are persisted outcomes — never HTTP 5xx. Transport
wait, headers, and session correlation never enter admission.
"""
import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ascend_op_eval import versioning
from ascend_op_eval.api import errors
from ascend_op_eval.api.auth import (
    require_caller,
    require_observer,
    require_read_caller,
    require_submit_caller,
)
from ascend_op_eval.api.contract import (
    DeploymentInfo,
    DeploymentListener,
    EvaluationProgress,
    EvaluationRequest,
    EvaluationResource,
    ReleaseVerification,
    StorageVersions,
    VersionInfo,
)
from ascend_op_eval.api.dependencies import AppContext, get_context, get_instance
from ascend_op_eval.api.errors import error_responses
from ascend_op_eval.api.schemas import Liveness, Readiness
from ascend_op_eval.api.submission import TERMINAL_STATES, HttpSubmission, Submission
from ascend_op_eval.api.submission import wait_until_terminal as wait_until_terminal
from ascend_op_eval.control.instance import EvaluationInstance
from ascend_op_eval.control.security import Caller
from ascend_op_eval.operator_input import OperatorRequest, PreflightRequest, to_evaluation_request

router = APIRouter()

SUBMIT_RESPONSES = {
    **error_responses(400, 401, 403, 409, 413, 422, 429, 500, 503, inflight_limit=True),
    202: {
        "model": EvaluationResource,
        "description": "Accepted or replayed evaluation still running.",
        "headers": {"Location": {
            "description": "Resource recovery URL.", "schema": {"type": "string"},
        }},
    },
}


@router.post("/evaluations", response_model=EvaluationResource, responses=SUBMIT_RESPONSES)
@router.post("/verify", response_model=EvaluationResource, responses=SUBMIT_RESPONSES)
@router.post("/benchmark", response_model=EvaluationResource, responses=SUBMIT_RESPONSES)
@router.post("/profile", response_model=EvaluationResource, responses=SUBMIT_RESPONSES)
async def submit_evaluation(
    request: Request,
    response: Response,
    evaluation_request: OperatorRequest,
    caller: Annotated[Caller, Depends(require_submit_caller)],
    instance: Annotated[EvaluationInstance, Depends(get_instance)],
    submission: Submission,
) -> EvaluationResource:
    checks = {
        "verify": ["correctness"],
        "benchmark": (
            ["correctness", "performance"]
            if evaluation_request.definition.reference is not None
            and (evaluation_request.triton_code is not None
                 or evaluation_request.candidate is not None)
            else ["performance"]
        ),
        "profile": ["profile"],
    }.get(request.scope["route"].path.rsplit("/", 1)[-1])
    try:
        internal_request = to_evaluation_request(evaluation_request, checks=checks)
    except ValueError as error:
        raise errors.invalid_request_schema(str(error)) from None
    return await _submit(request, response, internal_request, caller, instance, submission)


@router.post("/preflight", response_model=EvaluationResource, responses=SUBMIT_RESPONSES)
async def submit_preflight(
    request: Request,
    response: Response,
    preflight: PreflightRequest,
    caller: Annotated[Caller, Depends(require_submit_caller)],
    instance: Annotated[EvaluationInstance, Depends(get_instance)],
    submission: Submission,
) -> EvaluationResource:
    return await _submit(
        request, response, preflight.evaluation_request(), caller, instance, submission,
    )


async def _submit(
    request: Request, response: Response, internal_request: EvaluationRequest,
    caller: Caller, instance: EvaluationInstance, submission: HttpSubmission,
) -> EvaluationResource:
    outcome = await submission.admit(instance, caller, internal_request)
    if outcome.decision == "conflict":
        raise errors.idempotency_conflict()
    assert outcome.resource is not None
    return await submission.respond(request, response, instance, caller, outcome.resource)


@router.get(
    "/evaluations/{evaluation_id}", response_model=EvaluationResource,
    responses={
        **error_responses(401, 403, 404, 413, 422, 500),
        200: {"headers": {"Retry-After": {
            "description": "Polling delay for a pending resource, in seconds.",
            "schema": {"type": "string", "const": "1"},
        }}},
    },
)
async def get_evaluation(
    evaluation_id: str,
    response: Response,
    caller: Annotated[Caller, Depends(require_read_caller)],
    instance: Annotated[EvaluationInstance, Depends(get_instance)],
) -> EvaluationResource:
    resource = await asyncio.to_thread(
        instance.get, evaluation_id, caller
    )
    if resource is None:
        # Unknown, invisible, and invalidly shaped IDs are indistinguishable.
        raise errors.not_found()
    if resource.state not in TERMINAL_STATES:
        response.headers.update(errors.RETRY_AFTER_ONE)
    return resource


@router.get(
    "/evaluations/{evaluation_id}/progress", response_model=EvaluationProgress,
    responses=error_responses(401, 403, 404, 413, 422, 500),
)
async def get_evaluation_progress(
    evaluation_id: str,
    response: Response,
    caller: Annotated[Caller, Depends(require_read_caller)],
    instance: Annotated[EvaluationInstance, Depends(get_instance)],
) -> EvaluationProgress:
    progress = await asyncio.to_thread(instance.get_progress, evaluation_id, caller)
    if progress is None:
        raise errors.not_found()
    if progress.state not in TERMINAL_STATES:
        response.headers.update(errors.RETRY_AFTER_ONE)
    return progress


@router.get(
    "/version", response_model=VersionInfo,
    responses=error_responses(401, 403, 413, 500),
)
def get_version(
    context: Annotated[AppContext, Depends(get_context)],
    caller: Annotated[Caller, Depends(require_caller)],
) -> VersionInfo:
    """Report the running release to any authenticated caller.

    Identity is process-local: discovery answers while no worker can serve, and
    reports only what the release declares -- never deployment configuration.
    """
    settings = context.instance.settings
    identity = context.release
    return VersionInfo(
        schema_version="2.1",
        service_version=identity.service_version,
        api_versions=list(versioning.API_VERSIONS),
        default_api_version=versioning.DEFAULT_API_VERSION,
        evaluator_build=settings.evaluator_build,
        storage=StorageVersions(
            read_versions=list(versioning.STORAGE_READ_VERSIONS),
            write_version=versioning.STORAGE_WRITE_VERSION,
        ),
        default_protocol=versioning.DEFAULT_PROTOCOL,
        capabilities=list(versioning.CAPABILITIES),
        release=ReleaseVerification(
            mode=identity.mode,
            verified=identity.verified,
            unverified_reasons=list(identity.reasons),
            manifest_digest=identity.manifest_digest,
            source_revision=identity.source_revision,
            source_digest=identity.source_digest,
        ),
    )


@router.get(
    "/deployment", response_model=DeploymentInfo,
    responses=error_responses(401, 403, 413, 500),
)
def get_deployment(
    context: Annotated[AppContext, Depends(get_context)],
    caller: Annotated[Caller, Depends(require_caller)],
) -> DeploymentInfo:
    """Report deployment identity to any authenticated caller.

    Hardware profiles are discovered from fresh worker observations. This is
    identity discovery, not worker readiness; callers still wait for
    ``/readyz`` independently.
    """
    settings = context.instance.settings
    listeners = [DeploymentListener(
        protocol="http", host=settings.api_host, port=settings.api_port,
    )]
    if settings.api_tls_port is not None:
        listeners.append(DeploymentListener(
            protocol="https", host=settings.api_tls_host, port=settings.api_tls_port,
        ))
    return DeploymentInfo(
        schema_version="2.1",
        service_version=context.release.service_version,
        evaluator_build=settings.evaluator_build,
        listeners=listeners,
        capabilities=list(versioning.CAPABILITIES),
        method_capabilities=list(settings.method_capabilities),
        hardware_profiles=context.instance.store.active_hardware_profiles(),
    )


@router.get("/livez", response_model=Liveness, responses=error_responses(413, 500))
async def livez():
    """Constant process liveness; touches no store or worker state."""
    return {"status": "ok"}


@router.get("/health", response_model=Readiness, responses=error_responses(413, 500, 503))
@router.get("/readyz", response_model=Readiness, responses=error_responses(413, 500, 503))
async def readyz(instance: Annotated[EvaluationInstance, Depends(get_instance)]):
    ready = await asyncio.to_thread(instance.is_ready)
    if not ready:
        # No component detail: readiness failures are uniform.
        raise errors.not_ready()
    return {"ready": True}


@router.get(
    "/internal/metrics", response_class=Response, dependencies=[Depends(require_observer)],
    responses={
        **error_responses(401, 403, 404, 413, 500),
        200: {"content": {"application/openmetrics-text": {"schema": {"type": "string"}}}},
    },
)
def internal_metrics(context: Annotated[AppContext, Depends(get_context)]):
    metrics = context.instance.metrics
    if metrics is None:
        raise errors.not_found()
    return Response(
        content=metrics.render_openmetrics(),
        media_type="application/openmetrics-text; version=1.0.0; charset=utf-8",
    )
