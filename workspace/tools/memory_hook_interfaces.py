#!/usr/bin/env python3
"""M2 Interface Definitions for memory-hook-gateway.

This module defines the core interfaces for the M2 refactoring:
- IF-1: HostDelegate
- IF-2: PolicyRegistry
- IF-3: RouteTargetPolicy / WriteTargetPolicy
- IF-4: ArtifactSink / ErrorSink
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# IF-1: HostDelegate
# ---------------------------------------------------------------------------

class HostDelegate(ABC):
    """Interface for delegating hook events to host runtime."""

    @abstractmethod
    def can_handle(self) -> bool:
        """Return True if this delegate can handle the current context."""
        pass

    @abstractmethod
    def execute(
        self,
        event: str,
        raw_payload: str,
        payload: dict[str, Any],
    ) -> subprocess.CompletedProcess[str]:
        """Execute the delegate for the given event.

        Returns:
            Process result including return code and captured output
        """
        pass


# ---------------------------------------------------------------------------
# IF-2: PolicyRegistry
# ---------------------------------------------------------------------------

class PolicyRegistry(ABC):
    """Interface for policy lookups and validation."""

    @abstractmethod
    def get_policy(self, key: str) -> str | None:
        """Get a policy value by key."""
        pass

    @abstractmethod
    def validate(self, context: dict[str, Any]) -> list[str]:
        """Validate the given context against registered policies.

        Returns:
            List of error messages (empty if valid)
        """
        pass

    @abstractmethod
    def get_policy_pack(self, scope: str) -> dict[str, Any]:
        """Get a policy pack for the given scope.

        Returns:
            Dict containing policy pack with schema_version, policies, conflict_strategy
        """
        pass

    @abstractmethod
    def resolve_conflict(self, policy_key: str, values: list[str], strategy: str) -> str:
        """Resolve conflicting policy values using the given strategy.

        Args:
            policy_key: The policy key in conflict
            values: List of conflicting values
            strategy: Conflict resolution strategy

        Returns:
            Resolved policy value

        Raises:
            ValueError: If conflict cannot be resolved
        """
        pass


# ---------------------------------------------------------------------------
# IF-3: RouteTargetPolicy / WriteTargetPolicy
# ---------------------------------------------------------------------------

class RouteTargetPolicy(ABC):
    """Interface for route target resolution."""

    @abstractmethod
    def resolve(self, kind: str) -> str:
        """Resolve a route kind to a target path.

        Raises:
            ValueError: If the route kind is not supported
        """
        pass


class WriteTargetPolicy(ABC):
    """Interface for write target resolution."""

    @abstractmethod
    def get_targets(self) -> dict[str, Any]:
        """Get all write targets.

        Returns:
            Dict mapping target keys to paths
        """
        pass


class GatewayBusinessPolicy(ABC):
    """Interface for host/business policy used by gateway orchestration."""

    @abstractmethod
    def determine_project_scope(self, cwd: Path) -> str:
        """Resolve project scope from cwd."""
        pass

    @abstractmethod
    def get_project_canonical(self) -> dict[str, Path]:
        """Return project canonical mapping."""
        pass

    @abstractmethod
    def get_project_runtime_root(self) -> dict[str, Path]:
        """Return project runtime root mapping."""
        pass

    @abstractmethod
    def get_required_canonical(self) -> list[Path]:
        """Return required canonical files."""
        pass

    @abstractmethod
    def get_global_canonical(self) -> list[Path]:
        """Return global canonical files."""
        pass

    @abstractmethod
    def project_map_refs(self) -> list[str]:
        """Return project-map reference paths."""
        pass

    @abstractmethod
    def validate_project_map_files(self) -> list[str]:
        """Validate project-map contract files."""
        pass

    @abstractmethod
    def validate_unique_legal_system_contract(self) -> list[str]:
        """Validate unique legal system contract."""
        pass

    @abstractmethod
    def governance_frozen_tuple_blocker_errors(self) -> list[str]:
        """Return governance frozen tuple blocker errors."""
        pass

    @abstractmethod
    def event_contract_blocker_errors(self) -> list[str]:
        """Return event contract blocker errors."""
        pass

    @abstractmethod
    def decision_refs_for_scope(self, project_scope: str) -> list[str]:
        """Return decision refs for project scope."""
        pass

    @abstractmethod
    def lesson_refs_for_scope(self, project_scope: str) -> list[str]:
        """Return lesson refs for project scope."""
        pass

    @abstractmethod
    def docs_refs_for_scope(self, project_scope: str) -> list[str]:
        """Return docs refs for project scope."""
        pass

    @abstractmethod
    def truth_basis_for_scope(self, project_scope: str) -> dict[str, Any]:
        """Return truth basis package for project scope."""
        pass


# ---------------------------------------------------------------------------
# IF-4: ArtifactSink / ErrorSink
# ---------------------------------------------------------------------------

class ArtifactSink(ABC):
    """Interface for artifact output."""

    @abstractmethod
    def write(self, package: dict[str, Any]) -> dict[str, str]:
        """Write an artifact package.

        Returns:
            Dict with written artifact paths
        """
        pass

    @abstractmethod
    def ensure_dirs(self) -> None:
        """Ensure artifact directories exist."""
        pass


class ErrorSink(ABC):
    """Interface for error logging."""

    @abstractmethod
    def log(self, component: str, message: str, context: dict[str, Any]) -> None:
        """Log an error message."""
        pass
