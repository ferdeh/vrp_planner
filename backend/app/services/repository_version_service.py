"""Repository version metadata helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess

from app.models import schemas


@dataclass(frozen=True)
class RepositoryTarget:
    key: str
    title: str
    repo_name: str
    env_prefixes: tuple[str, ...]
    candidate_paths: tuple[Path, ...]


def get_repository_versions() -> schemas.RepositoryVersionResponse:
    """Return repository version metadata for planner and infra."""

    return schemas.RepositoryVersionResponse(
        generated_at=datetime.now(timezone.utc),
        repositories=[_load_repository_version(target) for target in _repository_targets()],
    )


def _repository_targets() -> tuple[RepositoryTarget, ...]:
    planner_repo_root = _local_planner_repo_root()

    return (
        RepositoryTarget(
            key="vrp_planner",
            title="VRP Planner",
            repo_name="vrp_planner",
            env_prefixes=("PLANNER", "VRP_PLANNER"),
            candidate_paths=tuple(
                path
                for path in (
                    _path_from_env("PLANNER_GIT_REPO_PATH", "VRP_PLANNER_GIT_REPO_PATH"),
                    Path("/workspace/vrp_planner"),
                    planner_repo_root,
                )
                if path is not None
            ),
        ),
        RepositoryTarget(
            key="vrp_infa",
            title="VRP Infra",
            repo_name="vrp_infa",
            env_prefixes=("INFRA", "VRP_INFRA", "INFA", "VRP_INFA"),
            candidate_paths=tuple(
                path
                for path in (
                    _path_from_env(
                        "INFRA_GIT_REPO_PATH",
                        "VRP_INFRA_GIT_REPO_PATH",
                        "INFA_GIT_REPO_PATH",
                        "VRP_INFA_GIT_REPO_PATH",
                    ),
                    Path("/workspace/vrp_infa"),
                    Path("/workspace/vrp_infra"),
                    planner_repo_root.parent / "vrp_infa",
                    planner_repo_root.parent / "vrp_infra",
                )
                if path is not None
            ),
        ),
    )


def _local_planner_repo_root() -> Path:
    current = Path(__file__).resolve()
    return current.parents[3]


def _path_from_env(*names: str) -> Path | None:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return Path(value)
    return None


def _load_repository_version(target: RepositoryTarget) -> schemas.RepositoryVersionItem:
    env_version = _version_from_env(target)
    if env_version is not None:
        return env_version

    for candidate in target.candidate_paths:
        if not candidate.exists():
            continue

        git_version = _version_from_git(target, candidate)
        if git_version is not None:
            return git_version

    return schemas.RepositoryVersionItem(
        key=target.key,
        title=target.title,
        repo_name=target.repo_name,
        available=False,
        source="unavailable",
        error="Git metadata tidak tersedia di runtime app.",
    )


def _version_from_env(target: RepositoryTarget) -> schemas.RepositoryVersionItem | None:
    for prefix in target.env_prefixes:
        commit_hash = os.getenv(f"{prefix}_GIT_COMMIT_HASH", "").strip()
        if not commit_hash:
            continue

        short_commit_hash = os.getenv(f"{prefix}_GIT_SHORT_COMMIT_HASH", "").strip() or commit_hash[:7]
        committed_at_raw = os.getenv(f"{prefix}_GIT_COMMITTED_AT", "").strip()
        committed_at = _parse_datetime(committed_at_raw) if committed_at_raw else None
        dirty = os.getenv(f"{prefix}_GIT_DIRTY", "").strip().lower() in {"1", "true", "yes", "on"}

        return schemas.RepositoryVersionItem(
            key=target.key,
            title=target.title,
            repo_name=target.repo_name,
            branch=os.getenv(f"{prefix}_GIT_BRANCH", "").strip() or None,
            commit_hash=commit_hash,
            short_commit_hash=short_commit_hash,
            commit_message=os.getenv(f"{prefix}_GIT_COMMIT_MESSAGE", "").strip() or None,
            committed_at=committed_at,
            dirty=dirty,
            source="env",
        )

    return None


def _version_from_git(
    target: RepositoryTarget,
    repo_path: Path,
) -> schemas.RepositoryVersionItem | None:
    try:
        commit_hash = _run_git(repo_path, "rev-parse", "HEAD")
        short_commit_hash = _run_git(repo_path, "rev-parse", "--short", "HEAD")
        branch = _run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
        commit_message = _run_git(repo_path, "log", "-1", "--format=%s")
        committed_at_raw = _run_git(repo_path, "log", "-1", "--date=iso-strict", "--format=%ad")
        dirty = bool(_run_git(repo_path, "status", "--porcelain"))
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        return None

    return schemas.RepositoryVersionItem(
        key=target.key,
        title=target.title,
        repo_name=target.repo_name,
        branch=None if branch == "HEAD" else branch,
        commit_hash=commit_hash,
        short_commit_hash=short_commit_hash,
        commit_message=commit_message,
        committed_at=_parse_datetime(committed_at_raw),
        dirty=dirty,
        source="git",
    )


def _run_git(repo_path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    return datetime.fromisoformat(normalized)
