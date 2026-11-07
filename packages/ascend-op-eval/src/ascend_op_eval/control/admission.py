"""Canonical admission for evaluation requests (design sections 3.1-3.2).

``admit()`` authorizes trial and rollout submissions against caller scopes
and canonicalizes the validated model. The wire contract's model validators
have already filled defaults and ordered checks/case indices, so ``model_dump(mode="json",
exclude_none=False)`` plus RFC 8785 canonicalization yields the exact bytes
whose SHA-256 is ``request_digest``. Transport metadata (``wait_seconds``,
``X-Session-ID``, headers) never enters the canonical form, and source bytes
are preserved verbatim.
"""
from collections.abc import Sequence
from dataclasses import dataclass

from ascend_op_eval.api.contract import Check, EvaluationRequest, GradeContext
from ascend_op_eval.control.security import Caller
from ascend_op_eval.serialization import canonical_json_bytes, sha256_hex


class ForbiddenError(Exception):
    """Public ``FORBIDDEN`` rejection for purpose/scope mismatches."""

    code = "FORBIDDEN"
    phase = "auth"
    retryable = False

    def __init__(self) -> None:
        super().__init__("caller lacks the required scope")


@dataclass(frozen=True)
class CanonicalAdmission:
    canonical_request: bytes
    request_digest: str
    reference_digest: str
    requested_checks: Sequence[Check]
    # Passive metadata retained for previously admitted grade records.
    catalog_binding: GradeContext | None
    execution_class: str | None = None


def admit(request: EvaluationRequest, caller: Caller) -> CanonicalAdmission:
    """Authorize a trial/rollout submission and canonicalize the model.

    Grade remains decodable for recovery of historical records, but no caller
    scope permits a new grade submission.
    """
    if request.purpose not in ("trial", "rollout") or "trial:submit" not in caller.scopes:
        raise ForbiddenError()
    dumped = request.model_dump(mode="json", exclude_none=False)
    canonical = canonical_json_bytes(dumped)
    return CanonicalAdmission(
        canonical_request=canonical,
        request_digest=sha256_hex(canonical),
        reference_digest=sha256_hex(request.reference_code.encode("utf-8")),
        requested_checks=tuple(request.checks),
        catalog_binding=None,
        execution_class=(
            request.method_execution.device if request.method_execution is not None else None
        ),
    )
