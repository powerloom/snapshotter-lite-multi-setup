"""Profile management commands for multi-profile support."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from snapshotter_cli.utils.console import Prompt, console
from snapshotter_cli.utils.profile import (
    ProfileConfig,
    copy_profile,
    create_profile,
    delete_profile,
    ensure_profile_structure,
    list_profiles,
    profile_exists,
)

profile_app = typer.Typer(
    name="profile",
    help="Manage CLI profiles for different wallet configurations",
    no_args_is_help=True,
)


@profile_app.command("list")
def list_profiles_command():
    """List all available profiles with their configurations."""
    # Ensure profile structure exists
    ensure_profile_structure()

    profiles = list_profiles()

    if not profiles:
        console.print(
            "No profiles found. Use 'powerloom-snapshotter-cli profile create' to create one.",
            style="yellow",
        )
        return

    # Create a table to display profiles
    table = Table(
        title="Available Profiles",
        show_header=True,
        header_style="bold blue",
        title_style="bold cyan",
    )
    table.add_column("Profile Name", style="magenta")
    table.add_column("Configurations", style="cyan", justify="center")
    table.add_column("Status", style="green")
    table.add_column("Created", style="dim")
    table.add_column("Description", style="white")

    config = ProfileConfig()
    default_profile = config.get_default_profile()
    last_used_profile = config.get_last_used_profile()

    for profile in profiles:
        status_parts = []
        if profile["name"] == default_profile:
            status_parts.append("🌟 Default")
        if profile["name"] == last_used_profile:
            status_parts.append("⏰ Last Used")

        status = " | ".join(status_parts) if status_parts else "—"

        created_date = profile.get("created", "Unknown")
        if created_date != "Unknown":
            # Format the ISO date to a more readable format
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(created_date)
                created_date = dt.strftime("%Y-%m-%d")
            except:
                pass

        table.add_row(
            profile["name"],
            str(profile.get("config_count", 0)),
            status,
            created_date,
            profile.get("description", ""),
        )

    console.print(table)
    console.print(
        "\nℹ️ Use 'powerloom-snapshotter-cli configure --profile <name>' to add configurations to a profile.",
        style="blue",
    )
    console.print(
        "ℹ️ Use 'powerloom-snapshotter-cli deploy --profile <name>' to deploy using a specific profile.",
        style="blue",
    )


@profile_app.command("create")
def create_profile_command(
    name: str = typer.Argument(..., help="Name for the new profile"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Description for the profile"
    ),
):
    """Create a new profile."""
    # Ensure profile structure exists
    ensure_profile_structure()

    # Validate profile name
    if not name or "/" in name or "\\" in name or "." in name:
        console.print(
            "❌ Invalid profile name. Use alphanumeric characters, hyphens, and underscores only.",
            style="red",
        )
        raise typer.Exit(1)

    if create_profile(name, description):
        console.print(
            f"💡 Use 'powerloom-snapshotter-cli configure --profile {name}' to add configurations.",
            style="blue",
        )
    else:
        raise typer.Exit(1)


@profile_app.command("delete")
def delete_profile_command(
    name: str = typer.Argument(..., help="Name of the profile to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """Delete a profile and all its configurations."""
    # Ensure profile structure exists
    ensure_profile_structure()

    if name == "default":
        console.print("❌ Cannot delete the default profile.", style="red")
        raise typer.Exit(1)

    if not profile_exists(name):
        console.print(f"❌ Profile '{name}' does not exist.", style="red")
        raise typer.Exit(1)

    # Count configurations in the profile
    from snapshotter_cli.utils.profile import PROFILES_DIR

    profile_dir = PROFILES_DIR / name
    config_count = len(list(profile_dir.glob(".env.*.*.*")))

    if not force:
        warning_msg = f"Are you sure you want to delete profile '{name}'?"
        if config_count > 0:
            warning_msg += f" This will delete {config_count} configuration(s)."

        if not typer.confirm(warning_msg):
            console.print("❌ Aborted.", style="yellow")
            raise typer.Exit(0)

    if delete_profile(name):
        if config_count > 0:
            console.print(
                f"✅ Deleted profile '{name}' and {config_count} configuration(s).",
                style="green",
            )
    else:
        raise typer.Exit(1)


@profile_app.command("copy")
def copy_profile_command(
    source: str = typer.Argument(..., help="Source profile name"),
    destination: str = typer.Argument(..., help="Destination profile name"),
):
    """Copy all configurations from one profile to another."""
    # Ensure profile structure exists
    ensure_profile_structure()

    # Validate destination profile name
    if (
        not destination
        or "/" in destination
        or "\\" in destination
        or "." in destination
    ):
        console.print(
            "❌ Invalid destination profile name. Use alphanumeric characters, hyphens, and underscores only.",
            style="red",
        )
        raise typer.Exit(1)

    if copy_profile(source, destination):
        console.print(
            f"💡 Use 'powerloom-snapshotter-cli deploy --profile {destination}' to use the copied profile.",
            style="blue",
        )
    else:
        raise typer.Exit(1)


@profile_app.command("set-default")
def set_default_profile_command(
    name: str = typer.Argument(..., help="Profile name to set as default"),
):
    """Set the default profile."""
    # Ensure profile structure exists
    ensure_profile_structure()

    if not profile_exists(name):
        console.print(f"❌ Profile '{name}' does not exist.", style="red")
        raise typer.Exit(1)

    config = ProfileConfig()
    if config.set_default_profile(name):
        console.print(f"✅ Set '{name}' as the default profile.", style="green")
        console.print(
            "ℹ️ Commands without --profile will now use this profile.", style="blue"
        )
    else:
        console.print("❌ Failed to set default profile.", style="red")
        raise typer.Exit(1)


@profile_app.command("show")
def show_profile_command(
    name: str = typer.Argument(..., help="Profile name to display"),
):
    """Show detailed information about a specific profile."""
    # Ensure profile structure exists
    ensure_profile_structure()

    if not profile_exists(name):
        console.print(f"❌ Profile '{name}' does not exist.", style="red")
        raise typer.Exit(1)

    from snapshotter_cli.utils.profile import PROFILES_DIR

    profile_dir = PROFILES_DIR / name

    # Get profile metadata
    config = ProfileConfig()
    profile_configs = config.list_profiles()
    profile_meta = profile_configs.get(name, {})

    # Count configurations by chain and market
    configs = {}
    for env_file in profile_dir.glob(".env.*.*.*"):
        parts = env_file.name.split(".")
        if len(parts) == 5:
            chain = parts[2].upper()
            market = parts[3].upper()
            source = parts[4].upper()

            if chain not in configs:
                configs[chain] = {}
            if market not in configs[chain]:
                configs[chain][market] = []
            configs[chain][market].append(source)

    # Display profile information
    console.print(f"\n[bold]Profile: {name}[/bold]")
    console.print(f"Path: {profile_dir}")

    if config.get_default_profile() == name:
        console.print("Status: 🌟 [bold green]Default Profile[/bold green]")
    if config.get_last_used_profile() == name:
        console.print("Status: ⏰ [dim]Last Used[/dim]")

    if "created" in profile_meta:
        console.print(f"Created: {profile_meta['created']}")
    if "description" in profile_meta:
        console.print(f"Description: {profile_meta['description']}")

    if configs:
        console.print("\n[bold]Configurations:[/bold]")
        for chain in sorted(configs.keys()):
            console.print(f"  [magenta]{chain}[/magenta]")
            for market in sorted(configs[chain].keys()):
                sources = ", ".join(configs[chain][market])
                console.print(f"    [cyan]{market}[/cyan] → [green]{sources}[/green]")
    else:
        console.print("\n[yellow]No configurations in this profile yet.[/yellow]")
        console.print(
            f"💡 Use 'powerloom-snapshotter-cli configure --profile {name}' to add configurations.",
            style="blue",
        )


@profile_app.command("export")
def export_profile_command(
    name: str = typer.Argument(..., help="Profile name to export"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file path (defaults to stdout)"
    ),
    include_credentials: bool = typer.Option(
        False,
        "--include-credentials",
        help="Include sensitive credentials (WARNING: Security risk!)",
    ),
):
    """Export a profile template (without credentials by default)."""
    # Ensure profile structure exists
    ensure_profile_structure()

    if not profile_exists(name):
        console.print(f"❌ Profile '{name}' does not exist.", style="red")
        raise typer.Exit(1)

    from snapshotter_cli.utils.deployment import parse_env_file_vars
    from snapshotter_cli.utils.profile import PROFILES_DIR

    profile_dir = PROFILES_DIR / name

    # Build export data
    export_data = {
        "profile_name": name,
        "configurations": [],
    }

    # Get profile metadata
    config = ProfileConfig()
    profile_configs = config.list_profiles()
    if name in profile_configs:
        export_data["metadata"] = profile_configs[name]

    # Process each configuration
    for env_file in profile_dir.glob(".env.*.*.*"):
        parts = env_file.name.split(".")
        if len(parts) == 5:
            chain = parts[2].upper()
            market = parts[3].upper()
            source = parts[4].upper()

            env_vars = parse_env_file_vars(str(env_file))

            config_data = {
                "chain": chain,
                "market": market,
                "source_chain": source,
                "settings": {},
            }

            # Include non-sensitive settings
            safe_keys = [
                "TELEGRAM_NOTIFICATION_COOLDOWN",
                "TELEGRAM_MESSAGE_THREAD_ID",
                "MAX_STREAM_POOL_SIZE",
                "CONNECTION_REFRESH_INTERVAL_SEC",
                "LITE_NODE_BRANCH",
                "LOCAL_COLLECTOR_IMAGE_TAG",
                "POWERLOOM_RPC_URL",
                "TELEGRAM_REPORTING_URL",
            ]

            for key in safe_keys:
                if key in env_vars:
                    config_data["settings"][key] = env_vars[key]

            # Optionally include credentials
            if include_credentials:
                credential_keys = [
                    "WALLET_HOLDER_ADDRESS",
                    "SIGNER_ACCOUNT_ADDRESS",
                    "SIGNER_ACCOUNT_PRIVATE_KEY",
                    "SOURCE_RPC_URL",
                    "TELEGRAM_CHAT_ID",
                ]
                for key in credential_keys:
                    if key in env_vars:
                        config_data["settings"][key] = env_vars[key]

            export_data["configurations"].append(config_data)

    # Output the export
    export_json = json.dumps(export_data, indent=2)

    if output:
        try:
            output.write_text(export_json)
            console.print(f"✅ Exported profile '{name}' to {output}", style="green")
            if include_credentials:
                console.print(
                    "⚠️ WARNING: Exported file contains sensitive credentials!",
                    style="bold yellow",
                )
        except IOError as e:
            console.print(f"❌ Error writing to file: {e}", style="red")
            raise typer.Exit(1)
    else:
        console.print(export_json)


@profile_app.command("import")
def import_profile_command(
    input_file: Path = typer.Argument(..., help="JSON file to import"),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Override the profile name from the file"
    ),
    merge: bool = typer.Option(
        False,
        "--merge",
        "-m",
        help="Merge with existing profile instead of creating new",
    ),
):
    """Import a profile from a JSON template file."""
    # Ensure profile structure exists
    ensure_profile_structure()

    if not input_file.exists():
        console.print(f"❌ File '{input_file}' does not exist.", style="red")
        raise typer.Exit(1)

    try:
        import_data = json.loads(input_file.read_text())
    except (json.JSONDecodeError, IOError) as e:
        console.print(f"❌ Error reading import file: {e}", style="red")
        raise typer.Exit(1)

    # Determine profile name
    profile_name = name or import_data.get("profile_name", "imported")

    # Validate profile name
    if (
        not profile_name
        or "/" in profile_name
        or "\\" in profile_name
        or "." in profile_name
    ):
        console.print(
            "❌ Invalid profile name. Use alphanumeric characters, hyphens, and underscores only.",
            style="red",
        )
        raise typer.Exit(1)

    # Check if profile exists
    if profile_exists(profile_name) and not merge:
        console.print(
            f"❌ Profile '{profile_name}' already exists. Use --merge to merge configurations.",
            style="red",
        )
        raise typer.Exit(1)

    # Create profile if needed
    if not profile_exists(profile_name):
        description = import_data.get("metadata", {}).get(
            "description", f"Imported profile"
        )
        create_profile(profile_name, description)

    from snapshotter_cli.utils.profile import PROFILES_DIR

    profile_dir = PROFILES_DIR / profile_name

    # Import configurations
    imported_count = 0
    skipped_count = 0

    for config in import_data.get("configurations", []):
        chain = config["chain"].lower()
        market = config["market"].lower()
        source = config["source_chain"].lower().replace("-", "_")

        from snapshotter_cli.utils.deployment import CONFIG_ENV_FILENAME_TEMPLATE

        filename = CONFIG_ENV_FILENAME_TEMPLATE.format(chain, market, source)
        env_path = profile_dir / filename

        if env_path.exists() and not merge:
            console.print(
                f"  ⏭️ Skipping {chain}/{market}/{source} - already exists",
                style="yellow",
            )
            skipped_count += 1
            continue

        # Build env file content
        env_lines = []
        for key, value in config.get("settings", {}).items():
            env_lines.append(f"{key}={value}")

        # Prompt for missing credentials if not present
        if "WALLET_HOLDER_ADDRESS" not in config.get("settings", {}):
            wallet = Prompt.ask(
                f"👉 Enter wallet address for {chain}/{market}/{source} (or press Enter to skip)",
                default="",
            )
            if wallet:
                env_lines.append(f"WALLET_HOLDER_ADDRESS={wallet}")

        if env_lines:
            env_path.write_text("\n".join(env_lines))
            console.print(f"  ✅ Imported {chain}/{market}/{source}", style="green")
            imported_count += 1
        else:
            console.print(
                f"  ⏭️ Skipping {chain}/{market}/{source} - no data", style="dim"
            )
            skipped_count += 1

    if imported_count > 0:
        console.print(
            f"✅ Successfully imported {imported_count} configuration(s) to profile '{profile_name}'",
            style="green",
        )
    if skipped_count > 0:
        console.print(f"ℹ️ Skipped {skipped_count} configuration(s)", style="yellow")

    if imported_count == 0 and skipped_count == 0:
        console.print("⚠️ No configurations found in import file", style="yellow")
