"""Fail-closed patient-scope authorization for trusted gateway identities."""
from __future__ import annotations

from dataclasses import dataclass


class PatientScopeDenied(PermissionError):
    """Raised when an identity is not entitled to a requested patient."""


def parse_entitlements(raw: str) -> dict[str, frozenset[str]]:
    result: dict[str, frozenset[str]] = {}
    for entry in raw.split(";"):
        caller, separator, patients = entry.partition("=")
        if separator and caller.strip():
            result[caller.strip()] = frozenset(p.strip() for p in patients.split(",") if p.strip())
    return result


@dataclass(frozen=True)
class PatientScopeAuthorizer:
    """Authorize one patient against an identity-to-patient entitlement map.

    The map is expected to come from a trusted gateway or a Kubernetes Secret;
    client supplied patient IDs never expand the caller's scope.
    """

    enabled: bool
    entitlements: dict[str, frozenset[str]]

    @classmethod
    def from_raw(cls, *, enabled: bool, raw: str) -> "PatientScopeAuthorizer":
        return cls(enabled=enabled, entitlements=parse_entitlements(raw))

    def authorize(self, *, patient_id: str | None, caller_id: str | None) -> None:
        if not self.enabled:
            return
        if not caller_id:
            raise PatientScopeDenied("X-Caller-Id is required for patient-scoped access.")
        if not patient_id:
            raise PatientScopeDenied("patient_id is required for patient-scoped access.")
        if patient_id not in self.entitlements.get(caller_id, frozenset()):
            raise PatientScopeDenied("Caller is not entitled to this patient.")
