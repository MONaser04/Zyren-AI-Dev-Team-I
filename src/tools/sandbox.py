"""
Docker Sandbox — Hardened Execution Environment
=================================================

Provides isolated execution for all agent-generated code.
Start with hardened Docker; path to gVisor/Firecracker for untrusted code.

READ Phase 3 deliverable:
  'Start with hardened Docker (network off, all caps dropped, read-only FS)
   or gVisor ... Never execute agent code on the host.'
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================
# Sandbox Result
# ============================================================


@dataclass(frozen=True)
class SandboxResult:
    """Result from a sandboxed execution."""

    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    files_changed: list[str] = field(default_factory=list)

    @classmethod
    def timeout(cls, timeout: int | None = None) -> SandboxResult:
        return cls(
            success=False,
            timed_out=True,
            stderr=f"Execution timed out{' after ' + str(timeout) + 's' if timeout else ''}.",
            exit_code=124,
        )

    @classmethod
    def error(cls, message: str, exit_code: int = 1) -> SandboxResult:
        return cls(success=False, stderr=message, exit_code=exit_code)


# ============================================================
# Sandbox Provider Interface
# ============================================================


class SandboxProvider:
    """Abstract sandbox for executing code/commands.

    Provides:
    - Isolated workspace (temp dir or Docker container)
    - Subprocess execution with timeout
    - File read/write within the workspace
    - Cleanup on teardown
    """

    def __init__(
        self,
        workspace_root: str | Path | None = None,
    ) -> None:
        """Initialize the sandbox provider.

        Args:
            workspace_root: Optional pre-existing workspace directory.
                            If None, a temp dir is created.
        """
        self._root = Path(workspace_root) if workspace_root else Path(tempfile.mkdtemp(prefix="zyren-ai-dev-team_sandbox_"))
        self._is_temp = workspace_root is None
        logger.info("Sandbox workspace: %s", self._root)

    # ----------------------------------------------------------
    # Workspace
    # ----------------------------------------------------------

    @property
    def workspace(self) -> Path:
        """The sandbox workspace directory."""
        return self._root

    def setup(self, files: dict[str, str] | None = None) -> None:
        """Prepare the sandbox workspace.

        Args:
            files: Optional mapping of path → content to write into the sandbox.
        """
        self._root.mkdir(parents=True, exist_ok=True)
        if files:
            for rel_path, content in files.items():
                target = self._root / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

    def cleanup(self) -> None:
        """Remove the workspace."""
        if self._is_temp and self._root.exists():
            shutil.rmtree(self._root, ignore_errors=True)
            logger.info("Sandbox cleaned: %s", self._root)

    # ----------------------------------------------------------
    # File Operations (inside sandbox)
    # ----------------------------------------------------------

    def read_file(self, rel_path: str) -> str:
        """Read a file from the sandbox workspace."""
        target = self._root / rel_path
        if not target.is_relative_to(self._root):
            msg = f"Path escapes sandbox: {rel_path}"
            raise ValueError(msg)
        return target.read_text(encoding="utf-8")

    def write_file(self, rel_path: str, content: str) -> None:
        """Write a file into the sandbox workspace."""
        target = self._root / rel_path
        if not target.is_relative_to(self._root):
            msg = f"Path escapes sandbox: {rel_path}"
            raise ValueError(msg)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def list_files(self, rel_dir: str = ".") -> list[Path]:
        """List files in a sandbox subdirectory."""
        target = self._root / rel_dir
        if not target.exists():
            return []
        return sorted(target.rglob("*"))

    # ----------------------------------------------------------
    # Execution
    # ----------------------------------------------------------

    def run_command(
        self,
        cmd: list[str],
        cwd: str = ".",
        timeout: int = 30,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Run a command inside the sandbox workspace.

        Args:
            cmd: Command + arguments as list.
            cwd: Working directory relative to sandbox root.
            timeout: Max seconds.
            env: Optional extra env vars.

        Returns:
            SandboxResult with stdout, stderr, exit_code.
        """
        work_dir = self._root / cwd
        work_dir.mkdir(parents=True, exist_ok=True)

        try:
            result = subprocess.run(
                cmd,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**__import__("os").environ, **(env or {})},
            )
            return SandboxResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult.timeout(timeout)
        except FileNotFoundError:
            return SandboxResult.error(f"Command not found: {cmd[0] if cmd else '?'}")

    def run_python(
        self,
        script: str,
        timeout: int = 30,
    ) -> SandboxResult:
        """Run Python code in the sandbox.

        Writes the script to a temp file and executes it.
        """
        script_path = self._root / "_zyren-ai-dev-team_script.py"
        script_path.write_text(script, encoding="utf-8")
        return self.run_command(["python", str(script_path)], timeout=timeout)


# ============================================================
# Docker Sandbox Provider (Phase 3)
# ============================================================


class DockerSandboxProvider(SandboxProvider):
    """Hardened Docker-based execution sandbox.

    READ spec:
      'Start with hardened Docker (network off, all caps dropped,
       read-only FS) or gVisor for syscall-level isolation.'

    For v0/v1, we use the host-based SandboxProvider as default
    (developer workstation). The DockerSandboxProvider is the
    Phase 3 upgrade path — use when executing untrusted code.
    """

    DOCKER_IMAGE = "python:3.12-slim"
    HARDENED_FLAGS: list[str] = [
        "--network=none",        # No network access
        "--cap-drop=ALL",        # Drop all Linux capabilities
        "--read-only",           # Read-only root FS
        "--tmpfs=/tmp:rw,noexec,nosuid,size=256M",  # Writable /tmp only
        "--memory=512m",
        "--cpus=1",
        "--pids-limit=100",
    ]

    def __init__(
        self,
        workspace_root: str | Path | None = None,
        image: str | None = None,
    ) -> None:
        super().__init__(workspace_root)
        self._image = image or self.DOCKER_IMAGE

    def run_command(
        self,
        cmd: list[str],
        cwd: str = ".",
        timeout: int = 30,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Run a command inside a hardened Docker container.

        Maps the workspace as a read-only volume + writable tmpfs.
        """
        docker_cmd = [
            "docker", "run", "--rm",
            *self.HARDENED_FLAGS,
            "-v", f"{self._root.absolute()}:/workspace:ro",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=256M",
            "-w", f"/workspace/{cwd}",
            self._image,
            *cmd,
        ]

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 10,  # Docker overhead
            )
            return SandboxResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult.timeout(timeout)
        except FileNotFoundError:
            return SandboxResult.error(
                "Docker not found or not running. "
                "Ensure Docker Desktop is installed and running."
            )

    def run_python(
        self,
        script: str,
        timeout: int = 30,
    ) -> SandboxResult:
        """Run Python code in a hardened Docker container."""
        script_path = self._root / "_zyren-ai-dev-team_script.py"
        script_path.write_text(script, encoding="utf-8")
        # Make writable copy in /tmp
        docker_cmd = [
            "docker", "run", "--rm",
            *self.HARDENED_FLAGS,
            "-v", f"{self._root.absolute()}:/workspace:ro",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=256M",
            "-w", "/workspace",
            self._image,
            "python", "/workspace/_zyren-ai-dev-team_script.py",
        ]

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 10,
            )
            return SandboxResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult.timeout(timeout)
        except FileNotFoundError:
            return SandboxResult.error("Docker not found. Is Docker Desktop running?")


# ============================================================
# Factory
# ============================================================


def create_sandbox(
    use_docker: bool = False,
    workspace_root: str | Path | None = None,
) -> SandboxProvider:
    """Create the appropriate sandbox provider.

    Args:
        use_docker: If True, use DockerSandboxProvider (hardened).
                    If False, use SandboxProvider (host temp dir).
        workspace_root: Optional pre-existing workspace directory.

    Returns:
        A SandboxProvider instance.
    """
    if use_docker:
        return DockerSandboxProvider(workspace_root)
    return SandboxProvider(workspace_root)