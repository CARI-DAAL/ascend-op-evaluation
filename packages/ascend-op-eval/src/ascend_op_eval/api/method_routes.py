"""Caller-owned custom-method-v1 registration and durable submission."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import Response

from ascend_op_eval.api import errors
from ascend_op_eval.api.auth import require_read_caller, require_submit_caller
from ascend_op_eval.api.contract import ErrorInfo, EvaluationRequest, EvaluationResource
from ascend_op_eval.api.dependencies import get_instance
from ascend_op_eval.api.submission import TERMINAL_STATES, HttpSubmission, Submission
from ascend_op_eval.control.broker import StorageError
from ascend_op_eval.control.instance import (
    EvaluationInstance,
)
from ascend_op_eval.control.security import Caller
from ascend_op_eval.methods.contracts import (
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
from ascend_op_eval.methods.registry import MethodRegistryError
from ascend_op_eval.serialization import canonical_json_bytes

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


def recover_method_submission(
    instance: EvaluationInstance, caller: Caller, options: HttpSubmission,
    submission: MethodSubmission,
) -> tuple[EvaluationResource, EvaluationRequest] | None:
    """Recover the originally admitted package even if the submitted alias has moved."""
    try:
        resource = instance.store.lookup_idempotent(caller.caller_id, options.idempotency_key)
    except StorageError:
        raise errors.internal() from None
    if resource is None:
        return None
    stored = instance.store.request_visible(resource.evaluation_id, caller, options.session_id)
    if stored is None or stored.method_execution is None:
        raise errors.idempotency_conflict()
    original = stored.method_execution.submission
    if canonical_json_bytes(original.model_dump(mode="json")) != canonical_json_bytes(
        submission.model_dump(mode="json")
    ):
        raise errors.idempotency_conflict()
    return resource, stored


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
    options: Submission,
) -> EvaluationResource:
    existing = await asyncio.to_thread(
        recover_method_submission, instance, caller, options, submission,
    )
    if existing is None:
        try:
            execution = await asyncio.to_thread(instance.methods.freeze, caller, submission)
        except MethodRegistryError as error:
            raise _registry_error(error) from None
        internal = EvaluationRequest(
            schema_version="2.1", purpose="trial", implementation="method", op_name="method",
            reference_code="", kernel_code="", checks=["method"],
            deadline_seconds=submission.deadline_seconds, method_execution=execution,
        )
    else:
        _, internal = existing
    outcome = await options.admit(instance, caller, internal)
    resource = outcome.resource
    if outcome.decision == "conflict":
        # A concurrent submission can win while this caller resolves a moving alias.
        winner = await asyncio.to_thread(
            recover_method_submission, instance, caller, options, submission,
        )
        if winner is None:
            raise errors.idempotency_conflict()
        resource, _ = winner
    assert resource is not None
    return await options.respond(request, response, instance, caller, resource)


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
