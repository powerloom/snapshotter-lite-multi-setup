"""Profile management utilities for multi-profile support."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from snapshotter_cli.utils.console import console

# Profile-related paths
CLI_CONFIG_DIR = Path.home() / ".powerloom-snapshotter-cli"
PROFILES_DIR = CLI_CONFIG_DIR / "profiles"
LEGACY_ENVS_DIR = CLI_CONFIG_DIR / "envs"
CONFIG_FILE = CLI_CONFIG_DIR / "config.json"
DEFAULT_PROFILE = "default"


class ProfileConfig:
    """Manages the global CLI configuration and profile settings."""

    def __init__(self):
        self.config_file = CONFIG_FILE
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load the configuration file or create a default one."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                console.print(f"⚠️ Error loading config file: {e}", style="yellow")

        # Return default configuration
        return {
            "default_profile": DEFAULT_PROFILE,
            "last_used_profile": DEFAULT_PROFILE,
            "profiles": {},
        }

    def save(self):
        """Save the current configuration to file."""
        try:
            # Ensure directory exists
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=2)
        except IOError as e:
            console.print(f"❌ Error saving config file: {e}", style="red")
            return False
        return True

    def get_default_profile(self) -> str:
        """Get the default profile name."""
        return self.config.get("default_profile", DEFAULT_PROFILE)

    def set_default_profile(self, profile_name: str) -> bool:
        """Set the default profile."""
        if not profile_exists(profile_name):
            console.print(f"❌ Profile '{profile_name}' does not exist.", style="red")
            return False

        self.config["default_profile"] = profile_name
        return self.save()

    def get_last_used_profile(self) -> str:
        """Get the last used profile name."""
        return self.config.get("last_used_profile", DEFAULT_PROFILE)

    def set_last_used_profile(self, profile_name: str) -> bool:
        """Set the last used profile."""
        self.config["last_used_profile"] = profile_name
        return self.save()

    def add_profile(self, profile_name: str, description: Optional[str] = None) -> bool:
        """Add a profile to the configuration."""
        if "profiles" not in self.config:
            self.config["profiles"] = {}

        self.config["profiles"][profile_name] = {
            "created": datetime.now().isoformat(),
            "description": description or f"Profile: {profile_name}",
        }
        return self.save()

    def remove_profile(self, profile_name: str) -> bool:
        """Remove a profile from the configuration."""
        if "profiles" in self.config and profile_name in self.config["profiles"]:
            del self.config["profiles"][profile_name]

            # Update default profile if needed
            if self.config.get("default_profile") == profile_name:
                self.config["default_profile"] = DEFAULT_PROFILE

            # Update last used profile if needed
            if self.config.get("last_used_profile") == profile_name:
                self.config["last_used_profile"] = DEFAULT_PROFILE

            return self.save()
        return True

    def list_profiles(self) -> Dict:
        """Get all profiles from configuration."""
        return self.config.get("profiles", {})


def profile_exists(profile_name: str) -> bool:
    """Check if a profile directory exists."""
    profile_dir = PROFILES_DIR / profile_name
    return profile_dir.exists() and profile_dir.is_dir()


def create_profile(profile_name: str, description: Optional[str] = None) -> bool:
    """Create a new profile directory and update configuration."""
    profile_dir = PROFILES_DIR / profile_name

    if profile_dir.exists():
        console.print(f"❌ Profile '{profile_name}' already exists.", style="red")
        return False

    try:
        # Create profile directory
        profile_dir.mkdir(parents=True, exist_ok=True)

        # Update configuration
        config = ProfileConfig()
        config.add_profile(profile_name, description)

        console.print(f"✅ Created profile: {profile_name}", style="green")
        return True
    except OSError as e:
        console.print(f"❌ Error creating profile: {e}", style="red")
        return False


def delete_profile(profile_name: str, force: bool = False) -> bool:
    """Delete a profile and all its configurations."""
    if profile_name == DEFAULT_PROFILE and not force:
        console.print("❌ Cannot delete the default profile.", style="red")
        return False

    profile_dir = PROFILES_DIR / profile_name

    if not profile_dir.exists():
        console.print(f"⚠️ Profile '{profile_name}' does not exist.", style="yellow")
        return False

    try:
        # Remove profile directory and all contents
        import shutil

        shutil.rmtree(profile_dir)

        # Update configuration
        config = ProfileConfig()
        config.remove_profile(profile_name)

        console.print(f"✅ Deleted profile: {profile_name}", style="green")
        return True
    except OSError as e:
        console.print(f"❌ Error deleting profile: {e}", style="red")
        return False


def copy_profile(source_profile: str, destination_profile: str) -> bool:
    """Copy all configurations from one profile to another."""
    source_dir = PROFILES_DIR / source_profile
    dest_dir = PROFILES_DIR / destination_profile

    if not source_dir.exists():
        console.print(
            f"❌ Source profile '{source_profile}' does not exist.", style="red"
        )
        return False

    if dest_dir.exists():
        console.print(
            f"❌ Destination profile '{destination_profile}' already exists.",
            style="red",
        )
        return False

    try:
        import shutil

        # Copy entire profile directory
        shutil.copytree(source_dir, dest_dir)

        # Update configuration
        config = ProfileConfig()
        config.add_profile(
            destination_profile,
            f"Copied from {source_profile} on {datetime.now().strftime('%Y-%m-%d')}",
        )

        console.print(
            f"✅ Copied profile from '{source_profile}' to '{destination_profile}'",
            style="green",
        )
        return True
    except OSError as e:
        console.print(f"❌ Error copying profile: {e}", style="red")
        return False


def list_profiles() -> List[Dict]:
    """List all available profiles with their details."""
    profiles = []
    config = ProfileConfig()
    profile_configs = config.list_profiles()

    # Ensure profiles directory exists
    if not PROFILES_DIR.exists():
        return profiles

    # Scan profile directories
    for profile_dir in PROFILES_DIR.iterdir():
        if profile_dir.is_dir():
            profile_name = profile_dir.name
            profile_info = {
                "name": profile_name,
                "path": str(profile_dir),
                "is_default": profile_name == config.get_default_profile(),
                "is_last_used": profile_name == config.get_last_used_profile(),
                "config_count": len(list(profile_dir.glob(".env.*.*.*"))),
            }

            # Add metadata from config file if available
            if profile_name in profile_configs:
                profile_info.update(profile_configs[profile_name])

            profiles.append(profile_info)

    return sorted(profiles, key=lambda x: x["name"])


def get_active_profile(explicit_profile: Optional[str] = None) -> str:
    """
    Determine the active profile based on priority:
    1. Explicit profile parameter
    2. POWERLOOM_PROFILE environment variable
    3. Default profile from config (set by 'profile set-default')
    4. Last used profile from config
    5. Hardcoded default profile
    """
    if explicit_profile:
        if not profile_exists(explicit_profile):
            console.print(
                f"⚠️ Profile '{explicit_profile}' does not exist. Using default profile.",
                style="yellow",
            )
            return DEFAULT_PROFILE
        return explicit_profile

    # Check environment variable
    env_profile = os.environ.get("POWERLOOM_PROFILE")
    if env_profile:
        if not profile_exists(env_profile):
            console.print(
                f"⚠️ Profile '{env_profile}' from POWERLOOM_PROFILE env var does not exist. Using default.",
                style="yellow",
            )
            return DEFAULT_PROFILE
        return env_profile

    # Check config for default profile (set by 'profile set-default')
    config = ProfileConfig()
    default = config.get_default_profile()
    if profile_exists(default):
        return default

    # Check for last used profile
    last_used = config.get_last_used_profile()
    if last_used != DEFAULT_PROFILE and profile_exists(last_used):
        return last_used

    # Fall back to hardcoded default
    return DEFAULT_PROFILE


def get_profile_env_path(profile: str, chain: str, market: str, source: str) -> Path:
    """Get the env file path for a specific profile and configuration."""
    profile_dir = PROFILES_DIR / profile
    from snapshotter_cli.utils.deployment import CONFIG_ENV_FILENAME_TEMPLATE

    filename = CONFIG_ENV_FILENAME_TEMPLATE.format(chain, market, source)
    return profile_dir / filename


def migrate_legacy_configs() -> bool:
    """
    Migrate existing configurations to the new profile structure.
    Moves all .env.*.*.* files from the legacy location to the default profile.
    """
    # Check if migration is needed
    if PROFILES_DIR.exists():
        # Already migrated or new installation
        return True

    if not LEGACY_ENVS_DIR.exists():
        # No legacy configs to migrate
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        create_profile(DEFAULT_PROFILE, "Default profile")
        return True

    console.print(
        "📦 Migrating existing configurations to profile structure...", style="blue"
    )

    try:
        # Create profiles directory structure
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        default_profile_dir = PROFILES_DIR / DEFAULT_PROFILE
        default_profile_dir.mkdir(exist_ok=True)

        # Find and move all env files
        env_files = list(LEGACY_ENVS_DIR.glob(".env.*.*.*"))
        migrated_count = 0

        for env_file in env_files:
            if env_file.is_file():
                # Move file to default profile
                new_path = default_profile_dir / env_file.name
                env_file.rename(new_path)
                migrated_count += 1
                console.print(f"  ✓ Migrated {env_file.name}", style="dim green")

        # Create/update configuration file
        config = ProfileConfig()
        config.add_profile(DEFAULT_PROFILE, "Migrated from legacy configuration")
        config.set_default_profile(DEFAULT_PROFILE)

        if migrated_count > 0:
            console.print(
                f"✅ Successfully migrated {migrated_count} configuration(s) to default profile",
                style="green",
            )
        else:
            console.print(
                "ℹ️ No existing configurations found. Created default profile.",
                style="yellow",
            )

        return True

    except OSError as e:
        console.print(f"❌ Error during migration: {e}", style="red")
        console.print(
            "Please manually backup your configurations and retry.", style="yellow"
        )
        return False


def ensure_profile_structure():
    """Ensure the profile directory structure exists and handle migration if needed."""
    if not PROFILES_DIR.exists():
        migrate_legacy_configs()
    elif not profile_exists(DEFAULT_PROFILE):
        # Ensure default profile exists
        create_profile(DEFAULT_PROFILE, "Default profile")
