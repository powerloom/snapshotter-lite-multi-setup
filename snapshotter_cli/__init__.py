"""Powerloom Snapshotter Node Management CLI"""

import subprocess
import sys
from pathlib import Path

import toml

# Read version from pyproject.toml
# Handle PyInstaller bundle case
if getattr(sys, "frozen", False):
    # We're running in a PyInstaller bundle
    # pyproject.toml is bundled in the root of _MEIPASS
    base_path = Path(sys._MEIPASS)
    pyproject_path = base_path / "pyproject.toml"
else:
    # Normal development mode
    pyproject_path = Path("pyproject.toml")

with open(pyproject_path, "r") as f:
    pyproject = toml.load(f)
    __version__ = pyproject["project"]["version"]

# Build-time commit - will be set during build process
__commit__ = None


def get_git_commit():
    """Get the current git commit hash (short version).

    Returns commit in this order of preference:
    1. Build-time commit (for PyInstaller binaries)
    2. Runtime git commit (for development)
    3. None if not available
    """
    # First, check if we have a build-time commit
    if __commit__:
        return __commit__

    # Check if we're in a PyInstaller bundle
    if getattr(sys, "frozen", False):
        # For PyInstaller bundles, we can't get git info
        # The commit should have been embedded at build time
        return None

    # Try to get git commit at runtime (for development)
    try:
        # Try to get git commit hash
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
            timeout=1,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return None


def get_version_string():
    """Get the full version string including git commit if available."""
    version = __version__
    commit = get_git_commit()

    # Check if we're in a PyInstaller bundle
    if getattr(sys, "frozen", False):
        if commit:
            return f"{version} (commit: {commit})"
        else:
            return f"{version} (binary)"

    # Check if we're installed via pip
    # If __file__ is in site-packages, we're likely pip-installed
    if "site-packages" in str(Path(__file__).resolve()):
        return f"{version} (pip)"

    # Development version with git commit
    if commit:
        return f"{version} (commit: {commit})"

    return version
