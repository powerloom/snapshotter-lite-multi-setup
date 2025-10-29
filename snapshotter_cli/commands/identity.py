import os
from glob import glob
from pathlib import Path
from typing import Dict, List, Optional

import typer
from rich.table import Table

from snapshotter_cli.utils.console import console

from ..utils.deployment import (
    CONFIG_DIR,
    CONFIG_ENV_FILENAME_TEMPLATE,
    parse_env_file_vars,
)
from ..utils.models import CLIContext

identity_app = typer.Typer(
    name="identity",
    help="Manage chain and market-specific identity configurations via namespaced .env files.",
    no_args_is_help=True,
)


def list_env_files_with_profiles(cli_context: CLIContext) -> List[Dict]:
    """Find all namespaced .env files across all profiles."""
    from snapshotter_cli.utils.profile import PROFILES_DIR, ensure_profile_structure

    # Ensure profile structure exists
    ensure_profile_structure()

    env_files_info = []
    available_chains = [x.lower() for x in cli_context.available_environments]
    available_markets = [x.lower() for x in cli_context.available_markets]

    # Search for env files in all profiles
    if PROFILES_DIR.exists():
        for profile_dir in PROFILES_DIR.iterdir():
            if profile_dir.is_dir():
                profile_name = profile_dir.name
                for file in profile_dir.glob(".env.*.*.*"):
                    parts = file.name.strip().split(".")
                    if len(parts) == 5:
                        chain, market, source_chain = (
                            parts[2].lower(),
                            parts[3].lower(),
                            parts[4],
                        )
                        if chain in available_chains and market in available_markets:
                            env_files_info.append(
                                {
                                    "path": file,
                                    "profile": profile_name,
                                    "chain": chain,
                                    "market": market,
                                    "source": source_chain,
                                }
                            )

    # Also check legacy locations for backward compatibility
    # Check old CONFIG_DIR location
    if CONFIG_DIR.exists():
        for file in CONFIG_DIR.glob(".env.*.*.*"):
            parts = file.name.strip().split(".")
            if len(parts) == 5:
                chain, market, source_chain = (
                    parts[2].lower(),
                    parts[3].lower(),
                    parts[4],
                )
                if chain in available_chains and market in available_markets:
                    env_files_info.append(
                        {
                            "path": file,
                            "profile": "[Legacy]",
                            "chain": chain,
                            "market": market,
                            "source": source_chain,
                        }
                    )

    # Check current directory
    for file in Path().glob(".env.*.*.*"):
        parts = file.name.strip().split(".")
        if len(parts) == 5:
            chain, market, source_chain = parts[2].lower(), parts[3].lower(), parts[4]
            if chain in available_chains and market in available_markets:
                # Avoid duplicates
                if not any(ef["path"].name == file.name for ef in env_files_info):
                    env_files_info.append(
                        {
                            "path": file,
                            "profile": "[CWD]",
                            "chain": chain,
                            "market": market,
                            "source": source_chain,
                        }
                    )

    return sorted(env_files_info, key=lambda x: (x["profile"], x["chain"], x["market"]))


@identity_app.command("list")
def list_identities(
    ctx: typer.Context,
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Filter by specific profile name"
    ),
):
    """List all configured identities (namespaced .env files) across all profiles."""
    cli_context: CLIContext = ctx.obj
    env_files_info = list_env_files_with_profiles(cli_context)

    # Filter by profile if specified
    if profile:
        env_files_info = [ef for ef in env_files_info if ef["profile"] == profile]

    if not env_files_info:
        if profile:
            console.print(
                f"No configurations found for profile '{profile}'.",
                style="yellow",
            )
            console.print(
                f"Use 'powerloom-snapshotter-cli configure --profile {profile}' to add configurations.",
                style="blue",
            )
        else:
            console.print(
                "No configurations found. Use 'powerloom-snapshotter-cli configure' to create one.",
                style="yellow",
            )
            console.print(
                "Or use 'powerloom-snapshotter-cli profile create' to create a new profile.",
                style="blue",
            )
        return

    # Set table title based on whether we're filtering
    if profile:
        table_title = f"Configured Identities for Profile: {profile}"
    else:
        table_title = "Configured Identities Across All Profiles"

    table = Table(
        title=table_title,
        show_header=True,
        header_style="bold blue",
        title_style="bold cyan",
    )
    table.add_column("Profile", style="bold magenta")
    table.add_column("Powerloom Chain", style="magenta")
    table.add_column("Market", style="cyan")
    table.add_column("Source Chain", style="green")
    table.add_column("Status", style="yellow")

    for env_file_info in env_files_info:
        env_file = env_file_info["path"]
        profile = env_file_info["profile"]
        chain = env_file_info["chain"].upper()
        market = env_file_info["market"].upper()
        source_chain = env_file_info["source"].upper()

        env_vars = parse_env_file_vars(str(env_file))

        # Determine configuration status
        status_parts = []
        if not env_vars.get("WALLET_HOLDER_ADDRESS"):
            status_parts.append("❌ No Wallet")
        if not env_vars.get("SIGNER_ACCOUNT_ADDRESS"):
            status_parts.append("❌ No Signer")
        if not env_vars.get("SIGNER_ACCOUNT_PRIVATE_KEY"):
            status_parts.append("❌ No Key")
        if not env_vars.get("SOURCE_RPC_URL"):
            status_parts.append("❌ No RPC")

        status = (
            "✓ Ready" if not status_parts else " ".join(status_parts[:2])
        )  # Show first 2 issues

        # Add profile indicator
        if profile == "[Legacy]":
            profile_display = f"[yellow]{profile}[/yellow]"
        elif profile == "[CWD]":
            profile_display = f"[dim]{profile}[/dim]"
        else:
            profile_display = profile

        table.add_row(profile_display, chain, market, source_chain, status)

    console.print(table)

    # Check for legacy files
    has_legacy = any(ef["profile"] in ["[Legacy]", "[CWD]"] for ef in env_files_info)
    if has_legacy:
        console.print(
            "\n⚠️ [yellow]Legacy configurations found. Run 'powerloom-snapshotter-cli profile list' to migrate them.[/yellow]",
            style="yellow",
        )

    console.print(
        "\nℹ️ Use 'powerloom-snapshotter-cli configure --profile <PROFILE>' to add configurations.",
        style="blue",
    )
    console.print(
        "ℹ️ Use 'powerloom-snapshotter-cli profile list' to manage profiles.",
        style="blue",
    )


@identity_app.command("show")
def show_identity(
    ctx: typer.Context,
    chain: str = typer.Option(
        ..., "--chain", "-c", help="Powerloom chain name (e.g., DEVNET, MAINNET)"
    ),
    market: str = typer.Option(
        ..., "--market", "-m", help="Data market name (e.g., UNISWAPV2)"
    ),
    source_chain: str = typer.Option(
        ..., "--source-chain", "-s", help="Source chain name (e.g., ETH-MAINNET)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Profile name to use"
    ),
):
    """Show the contents of a specific namespaced .env file."""
    from snapshotter_cli.utils.profile import get_active_profile, get_profile_env_path

    # Determine which profile to use
    active_profile = get_active_profile(profile)

    # Normalize inputs for filename
    norm_chain = chain.lower()
    norm_market = market.lower()
    norm_source = source_chain.lower().replace("-", "_")

    # Get env file path for the active profile
    env_path = get_profile_env_path(
        active_profile, norm_chain, norm_market, norm_source
    )

    # Also check legacy locations for backward compatibility
    if not env_path.exists():
        env_filename = CONFIG_ENV_FILENAME_TEMPLATE.format(
            norm_chain, norm_market, norm_source
        )

        # Check old CONFIG_DIR location
        legacy_path = CONFIG_DIR / env_filename
        if legacy_path.exists():
            console.print(
                f"⚠️ Found legacy env file. Consider migrating with 'profile list'.",
                style="yellow",
            )
            env_path = legacy_path
        else:
            # Check current directory
            cwd_env_path = Path(os.getcwd()) / env_filename
            if cwd_env_path.exists():
                console.print(
                    f"⚠️ Found legacy env file in current directory. Consider migrating with 'profile list'.",
                    style="yellow",
                )
                env_path = cwd_env_path

    if not env_path.exists():
        console.print(
            f"No configuration found for {chain}/{market}/{source_chain} in profile '{active_profile}'.",
            style="yellow",
        )
        console.print(
            f"Use 'powerloom-snapshotter-cli configure --profile {active_profile}' to create one.",
            style="blue",
        )
        return

    env_vars = parse_env_file_vars(str(env_path))

    console.print(f"\n[bold]Configuration for {chain}/{market}/{source_chain}[/bold]")
    console.print(f"Profile: [magenta]{active_profile}[/magenta]")
    console.print(f"File: {env_path}\n")

    # Display in sections
    console.print("[bold]Identity[/bold]")
    console.print(
        f"  Wallet Address: {env_vars.get('WALLET_HOLDER_ADDRESS', '[Not Set]')}"
    )
    console.print(
        f"  Signer Address: {env_vars.get('SIGNER_ACCOUNT_ADDRESS', '[Not Set]')}"
    )
    console.print(
        f"  Signer Private Key: {'[Set]' if env_vars.get('SIGNER_ACCOUNT_PRIVATE_KEY') else '[Not Set]'}"
    )

    console.print("\n[bold]RPC Configuration[/bold]")
    console.print(f"  Source RPC URL: {env_vars.get('SOURCE_RPC_URL', '[Not Set]')}")
    console.print(
        f"  Powerloom RPC URL: {env_vars.get('POWERLOOM_RPC_URL', '[Not Set]')}"
    )

    # Show other relevant configuration if present
    if "TELEGRAM_CHAT_ID" in env_vars or "TELEGRAM_REPORTING_URL" in env_vars:
        console.print("\n[bold]Notifications[/bold]")
        if "TELEGRAM_CHAT_ID" in env_vars:
            console.print(f"  Telegram Chat ID: {env_vars['TELEGRAM_CHAT_ID']}")
        if "TELEGRAM_REPORTING_URL" in env_vars:
            console.print(
                f"  Telegram Reporting URL: {env_vars['TELEGRAM_REPORTING_URL']}"
            )


@identity_app.command("delete")
def delete_identity(
    ctx: typer.Context,
    chain: str = typer.Option(
        ..., "--chain", "-c", help="Powerloom chain name (e.g., DEVNET, MAINNET)"
    ),
    market: str = typer.Option(
        ..., "--market", "-m", help="Data market name (e.g., UNISWAPV2)"
    ),
    source_chain: str = typer.Option(
        ..., "--source-chain", "-s", help="Source chain name (e.g., ETH-MAINNET)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Profile name to use"
    ),
):
    """Delete a specific namespaced .env file."""
    from snapshotter_cli.utils.profile import get_active_profile, get_profile_env_path

    # Determine which profile to use
    active_profile = get_active_profile(profile)

    # Normalize inputs for filename
    norm_chain = chain.lower()
    norm_market = market.lower()
    norm_source = source_chain.lower().replace("-", "_")

    # Get env file path for the active profile
    env_path = get_profile_env_path(
        active_profile, norm_chain, norm_market, norm_source
    )

    # Also check legacy locations for backward compatibility
    if not env_path.exists():
        env_filename = CONFIG_ENV_FILENAME_TEMPLATE.format(
            norm_chain, norm_market, norm_source
        )

        # Check old CONFIG_DIR location
        legacy_path = CONFIG_DIR / env_filename
        if legacy_path.exists():
            console.print(
                f"⚠️ Found legacy env file. Consider migrating with 'profile list'.",
                style="yellow",
            )
            env_path = legacy_path
        else:
            # Check current directory
            cwd_env_path = Path(os.getcwd()) / env_filename
            if cwd_env_path.exists():
                console.print(
                    f"⚠️ Found legacy env file in current directory. Consider migrating with 'profile list'.",
                    style="yellow",
                )
                env_path = cwd_env_path

    if not env_path.exists():
        console.print(
            f"No configuration found for {chain}/{market}/{source_chain} in profile '{active_profile}'.",
            style="yellow",
        )
        return

    if typer.confirm(
        f"Are you sure you want to delete the configuration for {chain}/{market}/{source_chain} from profile '{active_profile}'?"
    ):
        try:
            env_path.unlink()
            console.print(
                f"✅ Deleted configuration from profile '{active_profile}': {env_path}",
                style="green",
            )
        except OSError as e:
            console.print(f"Error deleting configuration: {e}", style="bold red")
            raise typer.Exit(1)
