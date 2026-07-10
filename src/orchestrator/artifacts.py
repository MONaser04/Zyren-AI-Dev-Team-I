"""
Artifact Manager — Phase 5
===========================
Manages build artifacts from orchestration runs:
- Source code files
- Test outputs
- Logs
- Reports
- Coverage data

Provides versioning, retrieval, and cleanup.
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Artifact:
    """A single build artifact."""
    workflow_id: str
    iteration: int
    artifact_type: str  # source, test, log, report, coverage
    path: str
    size_bytes: int
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class ArtifactManager:
    """Manages artifacts for a workflow run."""

    ROOT_DIR = Path("artifacts")

    def __init__(self, workflow_id: str | None = None) -> None:
        self.workflow_id = workflow_id or str(uuid.uuid4())[:8]
        self.run_dir = self.ROOT_DIR / self.workflow_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts: list[Artifact] = []
        self._index_path = self.run_dir / "index.json"
        self._load_index()

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------
    def _load_index(self) -> None:
        if self._index_path.exists():
            try:
                with open(self._index_path, encoding="utf-8") as f:
                    data = json.load(f)
                self.artifacts = [
                    Artifact(**a) for a in data.get("artifacts", [])
                ]
            except Exception:
                self.artifacts = []

    def _save_index(self) -> None:
        data = {
            "workflow_id": self.workflow_id,
            "artifacts": [
                {
                    "workflow_id": a.workflow_id,
                    "iteration": a.iteration,
                    "artifact_type": a.artifact_type,
                    "path": a.path,
                    "size_bytes": a.size_bytes,
                    "created_at": a.created_at,
                    "metadata": a.metadata,
                }
                for a in self.artifacts
            ],
        }
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # ------------------------------------------------------------------
    # Save artifacts
    # ------------------------------------------------------------------
    def save(
        self,
        content: str | bytes,
        artifact_type: str,
        iteration: int,
        filename: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Artifact:
        """Save content as an artifact."""
        if filename is None:
            filename = f"{artifact_type}_iter{iteration}_{uuid.uuid4().hex[:8]}"
            if isinstance(content, str):
                filename += ".txt"
            else:
                filename += ".bin"

        path = self.run_dir / filename
        if isinstance(content, str):
            path.write_text(content, encoding="utf-8")
        else:
            path.write_bytes(content)

        size = path.stat().st_size
        artifact = Artifact(
            workflow_id=self.workflow_id,
            iteration=iteration,
            artifact_type=artifact_type,
            path=str(path.relative_to(self.ROOT_DIR)),
            size_bytes=size,
            metadata=metadata or {},
        )
        self.artifacts.append(artifact)
        self._save_index()
        return artifact

    def save_file(
        self,
        src_path: Path,
        artifact_type: str,
        iteration: int,
        metadata: dict[str, Any] | None = None,
    ) -> Artifact:
        """Copy a file into artifacts."""
        dst = self.run_dir / f"{artifact_type}_iter{iteration}_{src_path.name}"
        shutil.copy2(src_path, dst)

        size = dst.stat().st_size
        artifact = Artifact(
            workflow_id=self.workflow_id,
            iteration=iteration,
            artifact_type=artifact_type,
            path=str(dst.relative_to(self.ROOT_DIR)),
            size_bytes=size,
            metadata=metadata or {},
        )
        self.artifacts.append(artifact)
        self._save_index()
        return artifact

    # ------------------------------------------------------------------
    # Retrieve artifacts
    # ------------------------------------------------------------------
    def get_latest(self, artifact_type: str) -> Artifact | None:
        """Get the most recent artifact of a type."""
        filtered = [a for a in self.artifacts if a.artifact_type == artifact_type]
        return max(filtered, key=lambda a: a.iteration) if filtered else None

    def get_by_iteration(
        self, artifact_type: str, iteration: int
    ) -> list[Artifact]:
        """Get artifacts of type from specific iteration."""
        return [
            a for a in self.artifacts
            if a.artifact_type == artifact_type and a.iteration == iteration
        ]

    def get_all(self, artifact_type: str | None = None) -> list[Artifact]:
        """Get all artifacts, optionally filtered by type."""
        if artifact_type:
            return [a for a in self.artifacts if a.artifact_type == artifact_type]
        return self.artifacts

    def read_text(self, artifact: Artifact) -> str:
        """Read artifact content as text."""
        full_path = self.ROOT_DIR / artifact.path
        return full_path.read_text(encoding="utf-8")

    def read_bytes(self, artifact: Artifact) -> bytes:
        """Read artifact content as bytes."""
        full_path = self.ROOT_DIR / artifact.path
        return full_path.read_bytes()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup_old(self, keep_last_n: int = 3) -> int:
        """Remove artifacts older than keep_last_n iterations."""
        iterations = sorted({a.iteration for a in self.artifacts})
        if len(iterations) <= keep_last_n:
            return 0

        remove_iters = set(iterations[:-keep_last_n])
        removed = 0
        for artifact in self.artifacts:
            if artifact.iteration in remove_iters:
                path = self.ROOT_DIR / artifact.path
                if path.exists():
                    path.unlink()
                removed += 1

        # Rebuild index
        self.artifacts = [a for a in self.artifacts if a.iteration not in remove_iters]
        self._save_index()
        return removed

    def delete_run(self) -> None:
        """Delete entire run directory."""
        shutil.rmtree(self.run_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def summary(self) -> dict[str, Any]:
        """Get artifact summary."""
        by_type: dict[str, int] = {}
        by_iter: dict[int, int] = {}
        total_size = 0

        for a in self.artifacts:
            by_type[a.artifact_type] = by_type.get(a.artifact_type, 0) + 1
            by_iter[a.iteration] = by_iter.get(a.iteration, 0) + 1
            total_size += a.size_bytes

        return {
            "workflow_id": self.workflow_id,
            "total_artifacts": len(self.artifacts),
            "total_size_mb": round(total_size / 1_048_576, 2),
            "by_type": by_type,
            "by_iteration": by_iter,
            "run_dir": str(self.run_dir),
        }


def create_artifact_manager(workflow_id: str | None = None) -> ArtifactManager:
    """Factory function."""
    return ArtifactManager(workflow_id)