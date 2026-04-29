"""Regression tests for profile vs market merge of config/compute repo env vars."""

from snapshotter_cli.utils.deployment import (
    apply_compute_repo_from_market,
    apply_snapshot_config_repo_from_market,
)
from snapshotter_cli.utils.models import ComputeConfig


def _cfg(repo: str, branch: str, commit: str | None = None) -> ComputeConfig:
    return ComputeConfig(repo=repo, branch=branch, commit=commit)


def test_snapshot_config_applies_full_bundle_when_repo_unset():
    env: dict[str, str] = {}
    apply_snapshot_config_repo_from_market(
        env,
        _cfg(
            "https://github.com/PowerLoom/snapshotter-configs.git",
            "eth_main",
            commit="abc123",
        ),
    )
    assert env["SNAPSHOT_CONFIG_REPO"] == "https://github.com/PowerLoom/snapshotter-configs.git"
    assert env["SNAPSHOT_CONFIG_REPO_BRANCH"] == "eth_main"
    assert env["SNAPSHOT_CONFIG_REPO_COMMIT"] == "abc123"


def test_snapshot_config_repo_override_skips_curated_branch_and_commit():
    """Profile may set only SNAPSHOT_CONFIG_REPO; curated branch/commit must not be merged."""
    env = {"SNAPSHOT_CONFIG_REPO": "https://github.com/myteam/custom-config.git"}
    apply_snapshot_config_repo_from_market(
        env,
        _cfg(
            "https://github.com/PowerLoom/snapshotter-configs.git",
            "eth_main",
            commit="deadbeef",
        ),
    )
    assert env == {"SNAPSHOT_CONFIG_REPO": "https://github.com/myteam/custom-config.git"}


def test_compute_repo_applies_full_bundle_when_repo_unset():
    env: dict[str, str] = {}
    apply_compute_repo_from_market(
        env,
        _cfg("https://github.com/PowerLoom/snapshotter-computes.git", "main", commit=None),
    )
    assert env["SNAPSHOTTER_COMPUTE_REPO"] == "https://github.com/PowerLoom/snapshotter-computes.git"
    assert env["SNAPSHOTTER_COMPUTE_REPO_BRANCH"] == "main"
    assert "SNAPSHOTTER_COMPUTE_REPO_COMMIT" not in env


def test_compute_repo_override_skips_curated_branch():
    env = {"SNAPSHOTTER_COMPUTE_REPO": "https://github.com/oss/computes.git"}
    apply_compute_repo_from_market(
        env,
        _cfg(
            "https://github.com/PowerLoom/snapshotter-computes.git",
            "upstream",
            commit="abc",
        ),
    )
    assert env.keys() == {"SNAPSHOTTER_COMPUTE_REPO"}
