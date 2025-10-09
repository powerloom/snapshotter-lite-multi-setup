import os
import shutil
import traceback
from pathlib import Path
from typing import Dict, List, Optional

import requests
import typer
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from snapshotter_cli.utils.changelog import display_changelog
from snapshotter_cli.utils.console import Prompt, console

from . import __version__, get_version_string
from .commands.configure import configure_command
from .commands.diagnose import diagnose_command
from .commands.identity import identity_app
from .commands.shell import shell_command
from .utils.config_helpers import get_credential, get_source_chain_rpc_url
from .utils.deployment import (
    CONFIG_DIR,
    CONFIG_ENV_FILENAME_TEMPLATE,
    deploy_snapshotter_instance,
    parse_env_file_vars,
    run_git_command,
)
from .utils.docker_utils import get_docker_container_status_for_instance
from .utils.evm import fetch_owned_slots
from .utils.models import (
    ChainConfig,
    ChainMarketData,
    CLIContext,
    ComputeConfig,
    MarketConfig,
    PowerloomChainConfig,
)
from .utils.system_checks import is_docker_running, list_snapshotter_screen_sessions

MARKETS_CONFIG_URL = (
    "https://raw.githubusercontent.com/powerloom/curated-datamarkets/main/sources.json"
)


def parse_selection_string(selection: str, max_value: int) -> List[int]:
    """Parse a selection string like '1,3-5,7' into a list of indices.

    Args:
        selection: String containing comma-separated numbers and ranges
        max_value: Maximum valid index (1-based)

    Returns:
        List of 0-based indices
    """
    indices = set()
    parts = selection.replace(" ", "").split(",")

    for part in parts:
        if not part:
            continue

        if "-" in part:
            # Handle range like "1-3"
            try:
                start, end = part.split("-", 1)
                start_idx = int(start) - 1
                end_idx = int(end) - 1
                if 0 <= start_idx <= end_idx < max_value:
                    indices.update(range(start_idx, end_idx + 1))
                else:
                    raise ValueError(f"Invalid range: {part}")
            except (ValueError, IndexError):
                raise ValueError(f"Invalid range format: {part}")
        else:
            # Handle single number
            try:
                idx = int(part) - 1
                if 0 <= idx < max_value:
                    indices.add(idx)
                else:
                    raise ValueError(f"Invalid number: {part}")
            except ValueError:
                raise ValueError(f"Invalid number format: {part}")

    return sorted(list(indices))


def fetch_markets_config() -> List[PowerloomChainConfig]:
    """Fetch markets configuration from GitHub"""
    try:
        response = requests.get(MARKETS_CONFIG_URL)
        response.raise_for_status()
        raw_data = response.json()
        return [PowerloomChainConfig(**chain) for chain in raw_data]
    except Exception as e:
        console.print(f"⚠️ Failed to fetch markets config: {e}", style="bold red")
        return []


def version_callback(value: bool):
    """Show version and exit."""
    if value:
        console.print(f"Powerloom Snapshotter CLI version: {get_version_string()}")
        raise typer.Exit()


def changelog_callback(value: bool):
    """Show changelog and exit."""
    if value:
        display_changelog()
        raise typer.Exit()


def load_default_config(
    ctx: typer.Context,
    version: bool = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
    changelog: bool = typer.Option(
        None,
        "--changelog",
        callback=changelog_callback,
        is_eager=True,
        help="Show changelog and exit.",
    ),
):
    """Load default configuration, available markets, and user settings"""
    try:
        markets_config = fetch_markets_config()
        if not markets_config:
            console.print(
                "❌ Could not fetch markets configuration. Cannot proceed.",
                style="bold red",
            )
            raise typer.Exit(1)

        chain_markets_map: Dict[str, ChainMarketData] = {}
        available_environments_set = set()
        for chain_config_obj in markets_config:
            chain_name_upper = chain_config_obj.powerloomChain.name.upper()
            available_environments_set.add(chain_name_upper)

            current_markets_for_chain: Dict[str, MarketConfig] = {}
            if chain_config_obj.dataMarkets:
                for market_def in chain_config_obj.dataMarkets:
                    current_markets_for_chain[market_def.name.upper()] = market_def

            chain_markets_map[chain_name_upper] = ChainMarketData(
                chain_config=chain_config_obj.powerloomChain,
                markets=current_markets_for_chain,
            )

        cli_obj = CLIContext(
            markets_config=markets_config,
            chain_markets_map=chain_markets_map,
            available_environments=available_environments_set,
            available_markets={
                market_name
                for chain_data in chain_markets_map.values()
                for market_name in chain_data.markets.keys()
            },
        )
        ctx.obj = cli_obj
    except Exception as e:
        console.print(f"🚨 Error in load_default_config: {e}", style="bold red")
        console.print(traceback.format_exc())
        raise typer.Exit(1)


app = typer.Typer(
    name="powerloom",
    help="Powerloom Snapshotter Node Management CLI",
    add_completion=False,
    callback=load_default_config,
    no_args_is_help=True,
)

app.add_typer(identity_app, name="identity")


@app.command()
def shell(ctx: typer.Context):
    """Start an interactive shell session for faster command execution."""
    shell_command(ctx, app)


# class Environment(str, Enum):
#     pass
#
# class DataMarket(str, Enum):
#     pass


@app.command()
def diagnose(
    clean: bool = typer.Option(
        False, "--clean", "-c", help="Clean up existing deployments"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force cleanup without confirmation"
    ),
    slot_id: Optional[str] = typer.Option(
        None, "--slot-id", "-s", help="Filter by specific slot ID"
    ),
    chain: Optional[str] = typer.Option(
        None, "--chain", help="Filter by chain name (e.g., 'mainnet', 'devnet')"
    ),
    market: Optional[str] = typer.Option(
        None,
        "--market",
        "-m",
        help="Filter by data market name (e.g., 'uniswapv2', 'aavev3')",
    ),
):
    """
    Run diagnostics on the system and optionally clean up existing deployments.
    Use filters to target specific slot IDs, chains, or markets.
    """
    diagnose_command(clean, force, slot_id=slot_id, chain=chain, market=market)


@app.command()
def deploy(
    ctx: typer.Context,
    environment: Optional[str] = typer.Option(
        None,
        "--env",
        "-e",
        help="Deployment environment (Powerloom chain name). If not provided, you will be prompted.",
    ),
    data_markets_opt: Optional[List[str]] = typer.Option(
        None,
        "--market",
        "-m",
        help="Data markets to deploy. If --env is provided but this is not, you will be prompted.",
    ),
    slots: Optional[List[int]] = typer.Option(
        None, "--slot", "-s", help="Specific slot IDs to deploy."
    ),
    wallet_address_opt: Optional[str] = typer.Option(
        None, "--wallet", "-w", help="Wallet address (0x...) holding the slots."
    ),
    signer_address_opt: Optional[str] = typer.Option(
        None, "--signer-address", help="Signer account address (0x...)."
    ),
    signer_key_opt: Optional[str] = typer.Option(
        None, "--signer-key", help="Signer account private key.", hide_input=True
    ),
):
    """Deploy snapshotter nodes for specified environment and data markets."""
    # --- Docker Check ---
    if not is_docker_running():
        console.print(
            "❌ Docker daemon is not running or not responsive. Please start Docker and try again.",
            style="bold red",
        )
        raise typer.Exit(1)
    console.print("🐳 Docker daemon is running.", style="green")

    cli_context: CLIContext = ctx.obj
    if not cli_context or not cli_context.chain_markets_map:
        console.print(
            "❌ Could not load markets configuration. Cannot proceed.", style="bold red"
        )
        raise typer.Exit(1)

    selected_powerloom_chain_name_upper: str
    env_config: Optional[ChainMarketData] = None

    base_snapshotter_clone_path = Path(os.getcwd()) / ".tmp_snapshotter_base_clone"

    try:
        if environment:
            selected_powerloom_chain_name_upper = environment.upper()
            env_config = cli_context.chain_markets_map.get(
                selected_powerloom_chain_name_upper
            )
            if not env_config:
                console.print(
                    f"❌ Invalid environment provided via --env: {environment}. Valid: {', '.join(cli_context.available_environments)}",
                    style="bold red",
                )
                raise typer.Exit(1)
        else:
            # Sort chains to prioritize MAINNET first
            all_powerloom_chains_from_config = sorted(
                cli_context.markets_config,
                key=lambda x: (
                    x.powerloomChain.name.upper() != "MAINNET",
                    x.powerloomChain.name.upper(),
                ),
            )
            if not all_powerloom_chains_from_config:
                console.print(
                    "❌ No Powerloom chains found in the remote configuration. Cannot proceed.",
                    style="bold red",
                )
                raise typer.Exit(1)

            chain_list_display = "\n".join(
                f"[bold green]{i+1}.[/] [cyan]{chain.powerloomChain.name.title()}[/]"
                for i, chain in enumerate(all_powerloom_chains_from_config)
            )
            panel = Panel(
                chain_list_display,
                title="[bold blue]Select Powerloom Chain for Deployment[/]",
                border_style="blue",
                padding=(1, 2),
            )
            console.print(panel)
            selected_chain_input = typer.prompt(
                "👉🏼 Select a Powerloom chain (number or name)", type=str
            )

            temp_chain_config_obj: Optional[PowerloomChainConfig] = None
            if selected_chain_input.isdigit():
                index = int(selected_chain_input) - 1
                if 0 <= index < len(all_powerloom_chains_from_config):
                    temp_chain_config_obj = all_powerloom_chains_from_config[index]
            else:
                temp_chain_config_obj = next(
                    (
                        cfg
                        for cfg in all_powerloom_chains_from_config
                        if cfg.powerloomChain.name.upper()
                        == selected_chain_input.upper()
                    ),
                    None,
                )

            if not temp_chain_config_obj:
                console.print(
                    f"❌ Invalid Powerloom chain selection: '{selected_chain_input}'.",
                    style="bold red",
                )
                raise typer.Exit(1)

            selected_powerloom_chain_name_upper = (
                temp_chain_config_obj.powerloomChain.name.upper()
            )
            env_config = cli_context.chain_markets_map.get(
                selected_powerloom_chain_name_upper
            )
            if not env_config:
                console.print(
                    f"❌ Could not find market data for selected chain {selected_powerloom_chain_name_upper}.",
                    style="bold red",
                )
                raise typer.Exit(1)

        if not env_config.markets:
            console.print(
                f"❌ No data markets found for {selected_powerloom_chain_name_upper} in sources.json.",
                style="bold red",
            )
            raise typer.Exit(1)

        console.print(
            f"🚀 Deploying to environment: [bold magenta]{selected_powerloom_chain_name_upper}[/bold magenta]...",
            style="bold green",
        )

        # --- Market Selection (moved before env loading) ---
        available_market_names_on_chain = list(env_config.markets.keys())
        final_selected_markets_str_list: List[str] = []

        if data_markets_opt:
            final_selected_markets_str_list = data_markets_opt
        else:
            if not available_market_names_on_chain:
                console.print(
                    f"🤷 No data markets available for {selected_powerloom_chain_name_upper} in sources.json.",
                    style="yellow",
                )
                raise typer.Exit(0)

            # Auto-select if only one market is available
            if len(available_market_names_on_chain) == 1:
                final_selected_markets_str_list = available_market_names_on_chain
                console.print(
                    f"✅ Auto-selected the only available market: [bold cyan]{available_market_names_on_chain[0]}[/bold cyan]",
                    style="green",
                )
            else:
                # Multiple markets available - show selection UI
                # Build market display with additional options
                market_lines = []
                for i, name in enumerate(available_market_names_on_chain):
                    market_lines.append(
                        f"[bold green]{i+1}.[/] [cyan]{name}[/] ([dim]Source: {env_config.markets[name].sourceChain}[/])"
                    )

                # Add special options
                market_lines.append(
                    "\n[bold yellow]0.[/] [yellow]Custom input (type market names manually)[/]"
                )
                if len(available_market_names_on_chain) > 1:
                    market_lines.append(
                        f"[bold yellow]A.[/] [yellow]Select all markets ({len(available_market_names_on_chain)} markets)[/]"
                    )

                market_display_list = "\n".join(market_lines)
                market_panel = Panel(
                    market_display_list,
                    title=f"[bold blue]Select Data Markets on {selected_powerloom_chain_name_upper}[/]",
                    border_style="blue",
                    padding=(1, 2),
                )
                console.print(market_panel)

                # Interactive selection
                while True:
                    selection = Prompt.ask(
                        "👉 Select markets (e.g., '1,3' or '1-3' or 'A' for all)",
                        default=(
                            "A" if len(available_market_names_on_chain) <= 3 else "1"
                        ),
                    )

                    selection = selection.strip().upper()

                    # Handle special cases
                    if selection == "0":
                        # Custom input - use original behavior
                        default_market_prompt = ",".join(
                            available_market_names_on_chain
                        )
                        markets_input_str = Prompt.ask(
                            f"👉 Enter market names (comma-separated)",
                            default=default_market_prompt,
                        )
                        final_selected_markets_str_list = [
                            m.strip() for m in markets_input_str.split(",") if m.strip()
                        ]
                        break
                    elif selection == "A" and len(available_market_names_on_chain) > 1:
                        # Select all
                        final_selected_markets_str_list = (
                            available_market_names_on_chain
                        )
                        console.print(
                            f"✅ Selected all {len(available_market_names_on_chain)} markets",
                            style="green",
                        )
                        break
                    else:
                        # Parse numeric selection
                        try:
                            indices = parse_selection_string(
                                selection, len(available_market_names_on_chain)
                            )
                            if indices:
                                final_selected_markets_str_list = [
                                    available_market_names_on_chain[i] for i in indices
                                ]
                                console.print(
                                    f"✅ Selected {len(final_selected_markets_str_list)} market(s): {', '.join(final_selected_markets_str_list)}",
                                    style="green",
                                )
                                break
                            else:
                                console.print(
                                    "❌ No valid selections made. Please try again.",
                                    style="red",
                                )
                        except ValueError as e:
                            console.print(
                                f"❌ Invalid selection: {e}. Please try again.",
                                style="red",
                            )

        # --- Load market-specific namespaced .env file (for first selected market) ---
        namespaced_env_content: Optional[Dict[str, str]] = None
        norm_pl_chain_name_for_file = selected_powerloom_chain_name_upper.lower()

        if final_selected_markets_str_list:
            # Use the first selected market for loading env file
            first_market_name = final_selected_markets_str_list[0]
            market_obj = env_config.markets[first_market_name.upper()]
            norm_market_name_for_file = first_market_name.lower()
            norm_source_chain_name_for_file = market_obj.sourceChain.lower().replace(
                "-", "_"
            )
            potential_config_filename = CONFIG_ENV_FILENAME_TEMPLATE.format(
                norm_pl_chain_name_for_file,
                norm_market_name_for_file,
                norm_source_chain_name_for_file,
            )

            # First check in config directory
            config_file_path = CONFIG_DIR / potential_config_filename
            if config_file_path.exists():
                console.print(
                    f"✓ Found namespaced .env for market {first_market_name}: {config_file_path}",
                    style="dim",
                )
                namespaced_env_content = parse_env_file_vars(str(config_file_path))
            else:
                # If not found in config directory, check current directory for backward compatibility
                cwd_config_file_path = Path(os.getcwd()) / potential_config_filename
                if cwd_config_file_path.exists():
                    console.print(
                        f"⚠️ Found legacy env file in current directory: {cwd_config_file_path}. Consider moving it to {CONFIG_DIR}",
                        style="yellow",
                    )
                    namespaced_env_content = parse_env_file_vars(
                        str(cwd_config_file_path)
                    )

        final_wallet_address = get_credential(
            "WALLET_HOLDER_ADDRESS",
            selected_powerloom_chain_name_upper,
            wallet_address_opt,
            namespaced_env_content,
        )
        if not final_wallet_address:
            error_message_lines = [
                f"❌ Wallet Holder Address for Powerloom chain [bold magenta]{selected_powerloom_chain_name_upper}[/bold magenta] could not be resolved.",
                f"   The CLI attempted to find it via:",
                f"     1. The --wallet CLI option",
                f"     2. The `WALLET_HOLDER_ADDRESS` shell environment variable",
                f"     3. A `WALLET_HOLDER_ADDRESS` entry in a `.env` file in your current directory",
                f"     4. A namespaced .env file for this chain/market combination",
                f"",
                f"💡 Run [bold cyan]configure[/bold cyan] to set up credentials.",
            ]
            console.print("\n".join(error_message_lines), style="bold red")
            raise typer.Exit(1)

        deploy_slots: Optional[List[int]] = slots
        if not deploy_slots:
            console.print(
                f"ℹ️ No specific slots provided. Fetching all slots owned by {final_wallet_address} on {env_config.chain_config.name}...",
                style="dim",
            )

            # Get protocol state contract address from the first market
            first_market = next(iter(env_config.markets.values()))
            protocol_state_contract_address = (
                first_market.powerloomProtocolStateContractAddress
            )

            fetched_slots_result = fetch_owned_slots(
                wallet_address=final_wallet_address,
                powerloom_chain_name=env_config.chain_config.name,
                rpc_url=str(env_config.chain_config.rpcURL).rstrip("/"),
                protocol_state_contract_address=protocol_state_contract_address,
            )
            if fetched_slots_result is None:
                console.print(
                    f"❌ Could not fetch slots. Please check errors above.",
                    style="bold red",
                )
                raise typer.Exit(1)
            if not fetched_slots_result:
                console.print(
                    f"🤷 No slots found for wallet {final_wallet_address}. Nothing to deploy.",
                    style="yellow",
                )
                raise typer.Exit(0)

            console.print(
                f"ℹ️ Found slots for wallet {final_wallet_address}: {fetched_slots_result}",
                style="dim",
            )
            deploy_all_slots_prompt = typer.prompt(
                "☑️ Do you want to deploy all of these fetched slots? (y/n)",
                default="y",
                show_default=True,
            )
            if deploy_all_slots_prompt.lower() == "n":
                while True:
                    start_slot_str = typer.prompt(
                        "🫸 ▶︎ Enter the start slot ID from the list above to deploy"
                    )
                    end_slot_str = typer.prompt(
                        "🫸 ▶︎ Enter the end slot ID from the list above to deploy (or same as start for single)"
                    )
                    try:
                        start_slot_val = int(start_slot_str)
                        end_slot_val = int(end_slot_str)
                        if (
                            start_slot_val not in fetched_slots_result
                            or end_slot_val not in fetched_slots_result
                        ):
                            console.print(
                                "❌ One or both slot IDs are not in the list of your owned slots. Please try again.",
                                style="red",
                            )
                            continue
                        if fetched_slots_result.index(
                            start_slot_val
                        ) > fetched_slots_result.index(end_slot_val):
                            console.print(
                                "❌ Start slot ID must appear before or be the same as end slot ID in your list. Please try again.",
                                style="red",
                            )
                            continue

                        start_idx = fetched_slots_result.index(start_slot_val)
                        end_idx = fetched_slots_result.index(end_slot_val)
                        deploy_slots = fetched_slots_result[start_idx : end_idx + 1]
                        break
                    except ValueError:
                        console.print(
                            "❌ Invalid slot ID format. Please enter numbers only.",
                            style="red",
                        )
                    except Exception as e:
                        console.print(
                            f"❌ Error processing slot selection: {e}. Please try again.",
                            style="red",
                        )
            else:
                deploy_slots = fetched_slots_result

        if not deploy_slots:
            console.print(f"🤷 No slots to deploy.", style="yellow")
            raise typer.Exit(0)

        console.print(
            f"🎰 Targeting slots for deployment: {deploy_slots}", style="bold blue"
        )

        if not env_config:
            console.print(
                "❌ Could not find market data for selected chain. Cannot proceed.",
                style="bold red",
            )
            raise typer.Exit(1)

        selected_market_objects: List[MarketConfig] = []
        for market_name_raw in final_selected_markets_str_list:
            market_name_upper = market_name_raw.strip().upper()
            if env_config and env_config.markets:
                market_obj = env_config.markets.get(market_name_upper)
            else:
                console.print(
                    f"❌ Could not find market data for selected chain. Cannot proceed.",
                    style="bold red",
                )
                raise typer.Exit(1)

            if not market_obj:
                error_market_list = (
                    available_market_names_on_chain
                    if available_market_names_on_chain
                    else []
                )
                console.print(
                    f"❌ Invalid market '{market_name_raw}' for {selected_powerloom_chain_name_upper}. Available: {', '.join(error_market_list)}",
                    style="bold red",
                )
                raise typer.Exit(1)
            selected_market_objects.append(market_obj)

        if not selected_market_objects:
            console.print("🤷 No data markets selected for deployment.", style="yellow")
            raise typer.Exit(0)

        # Get LITE_NODE_BRANCH from namespaced env content or use default
        lite_node_branch = "main"  # default branch
        if namespaced_env_content and "LITE_NODE_BRANCH" in namespaced_env_content:
            lite_node_branch = namespaced_env_content["LITE_NODE_BRANCH"]
            console.print(
                f"📌 Using LITE_NODE_BRANCH from configuration: [bold cyan]{lite_node_branch}[/bold cyan]",
                style="dim",
            )
        else:
            console.print(
                f"📌 No LITE_NODE_BRANCH found in configuration, using default: [bold cyan]{lite_node_branch}[/bold cyan]",
                style="dim",
            )

        console.print(
            f"🛠️ Preparing base snapshotter-lite-v2 clone at {base_snapshotter_clone_path}...",
            style="blue",
        )
        if base_snapshotter_clone_path.exists():
            console.print(
                f"  🗑️ Removing existing temporary clone directory: {base_snapshotter_clone_path}",
                style="dim",
            )
            try:
                shutil.rmtree(base_snapshotter_clone_path)
            except OSError as e:
                console.print(
                    f"  ❌ Could not remove existing temporary clone directory {base_snapshotter_clone_path}: {e}",
                    style="bold red",
                )
                raise typer.Exit(1)

        try:
            base_snapshotter_clone_path.mkdir(
                parents=True, exist_ok=False
            )  # exist_ok=False to ensure it was just created
        except OSError as e:
            console.print(
                f"  ❌ Could not create temporary clone directory {base_snapshotter_clone_path}: {e}",
                style="bold red",
            )
            raise typer.Exit(1)

        snapshotter_lite_repo_url = (
            "https://github.com/PowerLoom/snapshotter-lite-v2.git"
        )
        # Clone with the specified branch
        clone_command = [
            "git",
            "clone",
            "--branch",
            lite_node_branch,
            snapshotter_lite_repo_url,
            ".",
        ]
        if not run_git_command(
            clone_command,
            cwd=base_snapshotter_clone_path,
            desc=f"Cloning base snapshotter-lite-v2 repository from {{snapshotter_lite_repo_url}} (branch: {lite_node_branch})",
        ):
            console.print(
                f"❌ Failed to clone base snapshotter-lite-v2 repository from {snapshotter_lite_repo_url} (branch: {lite_node_branch}).",
                style="bold red",
            )
            # Cleanup already created directory before exiting
            if base_snapshotter_clone_path.exists():
                shutil.rmtree(base_snapshotter_clone_path)
            raise typer.Exit(1)
        console.print(
            f"  ✅ Base snapshotter-lite-v2 cloned successfully from branch: [bold cyan]{lite_node_branch}[/bold cyan].",
            style="green",
        )

        successful_deployments = 0
        failed_deployments = 0

        for market_conf_obj in selected_market_objects:
            console.print(
                f"📦 Processing market [bold cyan]{market_conf_obj.name}[/bold cyan] on [bold magenta]{selected_powerloom_chain_name_upper}[/bold magenta]...",
                style="green",
            )

            # --- Load market-specific namespaced .env file ---
            market_namespaced_env_content: Optional[Dict[str, str]] = None
            norm_pl_chain_name_for_file = selected_powerloom_chain_name_upper.lower()
            norm_market_name_for_file = market_conf_obj.name.lower()
            norm_source_chain_name_for_file = (
                market_conf_obj.sourceChain.lower().replace("-", "_")
            )
            potential_config_filename = CONFIG_ENV_FILENAME_TEMPLATE.format(
                norm_pl_chain_name_for_file,
                norm_market_name_for_file,
                norm_source_chain_name_for_file,
            )

            # First check in config directory
            config_file_path = CONFIG_DIR / potential_config_filename
            if config_file_path.exists():
                console.print(
                    f"✓ Found namespaced .env for market {market_conf_obj.name}: {config_file_path}",
                    style="dim",
                )
                market_namespaced_env_content = parse_env_file_vars(
                    str(config_file_path)
                )
            else:
                # Check current directory for backward compatibility
                cwd_config_file_path = Path(os.getcwd()) / potential_config_filename
                if cwd_config_file_path.exists():
                    console.print(
                        f"⚠️ Found legacy env file in current directory: {cwd_config_file_path}. Consider moving it to {CONFIG_DIR}",
                        style="yellow",
                    )
                    market_namespaced_env_content = parse_env_file_vars(
                        str(cwd_config_file_path)
                    )

            # --- Resolve Signer Credentials & Source RPC URL FOR THIS MARKET ---
            # Uses the loaded market_namespaced_env_content for this specific market
            market_signer_address = get_credential(
                "SIGNER_ACCOUNT_ADDRESS",
                selected_powerloom_chain_name_upper,
                signer_address_opt,
                market_namespaced_env_content,
            )
            if not market_signer_address:
                error_message_lines_signer_addr = [
                    f"❌ Signer Address for market [bold cyan]{market_conf_obj.name}[/] on [bold magenta]{selected_powerloom_chain_name_upper}[/bold magenta] not resolved.",
                    f"   Looked via: CLI option, SIGNER_ACCOUNT_ADDRESS env var, namespaced .env ({potential_config_filename})",
                ]
                console.print(
                    "\n".join(error_message_lines_signer_addr), style="bold red"
                )
                failed_deployments += len(deploy_slots)
                continue

            market_signer_key = get_credential(
                "SIGNER_ACCOUNT_PRIVATE_KEY",
                selected_powerloom_chain_name_upper,
                signer_key_opt,
                market_namespaced_env_content,
            )
            if not market_signer_key:
                error_message_lines_signer_key = [
                    f"❌ Signer Key for market [bold cyan]{market_conf_obj.name}[/] on [bold magenta]{selected_powerloom_chain_name_upper}[/bold magenta] not resolved.",
                    f"   Looked via: CLI option, SIGNER_ACCOUNT_PRIVATE_KEY env var, namespaced .env ({potential_config_filename})",
                ]
                console.print(
                    "\n".join(error_message_lines_signer_key), style="bold red"
                )
                failed_deployments += len(deploy_slots)
                continue

            console.print(
                f"🔑 Using Signer: {market_signer_address} for market {market_conf_obj.name}",
                style="bold blue",
            )

            source_rpc_url = get_source_chain_rpc_url(
                market_conf_obj.sourceChain, market_namespaced_env_content
            )
            if not source_rpc_url:
                error_message_lines_source_rpc = [
                    f"❌ RPC URL for source chain [bold yellow]{market_conf_obj.sourceChain}[/bold yellow] (market {market_conf_obj.name}) not found.",
                    f"   Looked via: SOURCE_RPC_{market_conf_obj.sourceChain.upper().replace('-', '_')} env var, CWD .env, namespaced .env ({potential_config_filename})",
                ]
                console.print("\n".join(error_message_lines_source_rpc), style="red")
                failed_deployments += len(deploy_slots)
                continue

            for idx, slot_id_val in enumerate(deploy_slots):
                # Build base args for build.sh
                base_args = (
                    "--skip-credential-update"
                    if idx == 0
                    else "--no-collector --skip-credential-update"
                )

                # Determine data market contract number based on market name
                market_name = market_conf_obj.name.upper()
                if market_name == "AAVEV3":
                    data_market_number = "1"
                elif market_name == "UNISWAPV2":
                    data_market_number = "2"
                else:
                    # Default to 1 for unknown markets
                    data_market_number = "1"

                # Add data market contract number
                base_args = (
                    f"{base_args} --data-market-contract-number {data_market_number}"
                )

                # Add --devnet flag if deploying to devnet
                if selected_powerloom_chain_name_upper == "DEVNET":
                    build_sh_args_for_instance = f"--devnet {base_args}"
                else:
                    build_sh_args_for_instance = base_args

                console.print(
                    f"   🔩 Deploying slot {slot_id_val} for market {market_conf_obj.name} (Source RPC: {source_rpc_url})",
                    style="green",
                )
                success = deploy_snapshotter_instance(
                    powerloom_chain_config=env_config.chain_config,
                    market_config=market_conf_obj,
                    slot_id=slot_id_val,
                    signer_address=market_signer_address,
                    signer_private_key=market_signer_key,
                    source_chain_rpc_url=source_rpc_url,
                    base_snapshotter_lite_repo_path=base_snapshotter_clone_path,
                    build_sh_args_param=build_sh_args_for_instance,
                )
                if success:
                    successful_deployments += 1
                else:
                    failed_deployments += 1
                    console.print(
                        f"❌ Failed deployment for slot {slot_id_val}, market {market_conf_obj.name}.",
                        style="bold red",
                    )

        console.print("\n[bold]----- Deployment Summary -----[/bold]")
        if successful_deployments > 0:
            console.print(
                f"✅ Successfully deployed {successful_deployments} snapshotter instance(s).",
                style="bold green",
            )
        if failed_deployments > 0:
            console.print(
                f"❌ Failed to deploy {failed_deployments} snapshotter instance(s).",
                style="bold red",
            )
        if successful_deployments == 0 and failed_deployments == 0:
            console.print(
                "🤷 No deployments were attempted or completed.", style="yellow"
            )

    finally:
        # --- Cleanup temporary base clone ---
        if base_snapshotter_clone_path.exists():
            console.print(
                f"🧹 Cleaning up temporary base snapshotter clone at {base_snapshotter_clone_path}...",
                style="dim",
            )
            try:
                shutil.rmtree(base_snapshotter_clone_path)
                console.print("  ✅ Cleanup successful.", style="dim green")
            except OSError as e:
                console.print(
                    f"  ⚠️ Error cleaning up temporary clone {base_snapshotter_clone_path}: {e}",
                    style="yellow",
                )


app.command("configure")(configure_command)


@app.command()
def status(
    ctx: typer.Context,
    environment: Optional[str] = typer.Option(
        None, "--env", "-e", help="Filter by Powerloom chain environment name."
    ),
    data_market: Optional[str] = typer.Option(
        None, "--market", "-m", help="Filter by data market name."
    ),
):
    """
    Show status of deployed snapshotter instances (screen sessions and Docker containers).
    Optionally filter by environment and/or data market.
    """
    console.print("📊 Checking snapshotter instances status...", style="bold magenta")
    if environment:
        console.print(
            f"🔍 Filtering for environment: [bold cyan]{environment}[/bold cyan]",
            style="dim",
        )
    if data_market:
        console.print(
            f"🔍 Filtering for data market: [bold cyan]{data_market}[/bold cyan]",
            style="dim",
        )

    all_screen_sessions = list_snapshotter_screen_sessions()
    filtered_sessions = []

    if not all_screen_sessions:
        console.print("🤷 No running screen sessions found", style="yellow")
        return

    for session in all_screen_sessions:
        session_name = session["name"]
        parsed_chain_name = None
        parsed_market_name = None
        parsed_slot_id = None

        # Try new format first (pl_{chain}_{market}_{slot_id})
        if session_name.startswith("pl_") and session_name.count("_") >= 3:
            try:
                name_parts_str = session_name[3:]  # Remove "pl_"
                name_parts_list = name_parts_str.split("_")

                parsed_slot_id = name_parts_list[-1]
                parsed_chain_name = name_parts_list[0]
                parsed_market_name = "_".join(name_parts_list[1:-1])

                # Validate slot_id is a number
                if not parsed_slot_id.isdigit():
                    parsed_chain_name, parsed_market_name, parsed_slot_id = (
                        None,
                        None,
                        None,
                    )
                    console.print(
                        f"  [dim yellow]⚠️ Skipping session '{session_name}': Slot ID part '{parsed_slot_id}' is not a number.[/dim]"
                    )
            except IndexError:
                console.print(
                    f"  [dim yellow]⚠️ Could not parse new format for session '{session_name}'.[/dim]"
                )
                parsed_chain_name, parsed_market_name, parsed_slot_id = None, None, None

        # Try legacy format if new format didn't match
        if not parsed_chain_name:
            # Legacy format: powerloom-{chain}-{market}-{slot_id}
            # or snapshotter-lite-v2-{slot_id}-{chain}-{market}
            try:
                if session_name.startswith("powerloom-"):
                    parts = session_name.split("-")
                    if len(parts) >= 4:
                        if parts[1] in ["premainnet", "testnet", "mainnet"]:
                            parsed_chain_name = parts[1]
                            parsed_market_name = parts[2]
                            parsed_slot_id = parts[3] if parts[3].isdigit() else None
                elif session_name.startswith("snapshotter-lite-v2-"):
                    parts = session_name.split("-")
                    if len(parts) >= 5 and parts[3] in [
                        "MAINNET",
                        "DEVNET",
                        "mainnet",
                        "devnet",
                    ]:
                        parsed_slot_id = parts[2] if parts[2].isdigit() else None
                        parsed_chain_name = parts[3].lower()
                        parsed_market_name = parts[4]
            except Exception:
                console.print(
                    f"  [dim yellow]⚠️ Could not parse legacy format for session '{session_name}'.[/dim]"
                )

        passes_env_filter = True
        if environment and parsed_chain_name:
            passes_env_filter = parsed_chain_name.lower() == environment.lower()
        elif environment and not parsed_chain_name:
            passes_env_filter = False

        passes_market_filter = True
        if data_market and parsed_market_name:
            passes_market_filter = parsed_market_name.lower() == data_market.lower()
        elif data_market and not parsed_market_name:
            passes_market_filter = False

        if passes_env_filter and passes_market_filter:
            session_details = {
                **session,
                "chain_name": parsed_chain_name or "N/A",
                "market_name": parsed_market_name or "N/A",
                "slot_id": parsed_slot_id or "N/A",
            }
            filtered_sessions.append(session_details)

    if not filtered_sessions:
        if environment or data_market:
            console.print(
                "🤷 No snapshotter instances found matching your filter criteria.",
                style="yellow",
            )
        else:
            # This case should ideally be caught by the initial `all_screen_sessions` check,
            # but as a fallback if parsing fails for all.
            console.print(
                "🤷 No processable snapshotter screen sessions found.", style="yellow"
            )
        return

    table = Table(
        title="Snapshotter Instances Status", show_header=True, header_style="bold blue"
    )
    table.add_column("Powerloom Chain", style="magenta", min_width=15)
    table.add_column("Data Market", style="cyan", min_width=20)
    table.add_column("Slot ID", style="green", min_width=7)
    table.add_column("Full Session Name", style="dim", min_width=25)
    table.add_column("PID", style="magenta", min_width=7)
    table.add_column("Screen Status", style="green")
    table.add_column("Docker Containers", style="dim")

    for session_detail in filtered_sessions:
        # session_name = session_detail["name"] # Original full name for Docker search, no longer primary key

        # Prepare params for the updated Docker search function
        parsed_slot_id = session_detail["slot_id"]
        parsed_chain_name_for_docker = session_detail[
            "chain_name"
        ]  # This is already parsed
        parsed_market_name_for_docker = session_detail[
            "market_name"
        ]  # This is already parsed

        # Convert to UPPER for the docker utility, ensure they are not "N/A"
        chain_name_upper_for_docker = (
            parsed_chain_name_for_docker.upper()
            if parsed_chain_name_for_docker != "N/A"
            else None
        )
        market_name_upper_for_docker = (
            parsed_market_name_for_docker.upper()
            if parsed_market_name_for_docker != "N/A"
            else None
        )
        slot_id_for_docker = parsed_slot_id if parsed_slot_id != "N/A" else None

        docker_containers = []  # Default to empty list
        if (
            chain_name_upper_for_docker and market_name_upper_for_docker
        ):  # slot_id can be None for collector search
            docker_containers = get_docker_container_status_for_instance(
                slot_id=slot_id_for_docker,
                chain_name_upper=chain_name_upper_for_docker,
                market_name_upper=market_name_upper_for_docker,
            )
        elif (
            parsed_slot_id != "N/A"
        ):  # Fallback if only slot_id is available and valid (less likely to match well)
            console.print(
                f"[dim yellow]⚠️ Only slot ID {parsed_slot_id} is available for Docker search for session '{session_detail['name']}'. Results may be limited or incorrect.[/dim]"
            )
            # Potentially call with only slot_id if the utility supported it, or skip.
            # For now, the utility expects chain & market for effective filtering.

        docker_info_parts = []
        if docker_containers:
            for dc in docker_containers:
                dc_status_color = (
                    "green"
                    if "Up" in dc["status"]
                    else ("yellow" if "Exited" in dc["status"] else "red")
                )
                docker_info_parts.append(
                    f"  - {dc['name']} ([{dc_status_color}]{dc['status']}[/{dc_status_color}])"
                )
        else:
            docker_info_parts.append(
                "  [dim]No matching Docker containers found.[/dim]"
            )

        docker_info_str = "\n".join(
            docker_info_parts
        )  # Use literal \n for Rich table cell

        table.add_row(
            session_detail["chain_name"],
            session_detail["market_name"],
            session_detail["slot_id"],
            session_detail["name"],  # Full original name
            session_detail["pid"],
            session_detail["status_str"],
            docker_info_str,
        )

    console.print(table)


@app.command(name="list")
def list_chains_and_markets(ctx: typer.Context):
    """
    Display available Powerloom chains and their data markets
    """
    cli_context: CLIContext = ctx.obj
    chain_markets_map = cli_context.chain_markets_map

    tree = Tree("🌐 [bold cyan]Available Powerloom Chains[/]")

    for chain_name, chain_data_val in sorted(
        chain_markets_map.items()
    ):  # sorted for consistent order
        chain_config_val = chain_data_val.chain_config
        markets_dict = chain_data_val.markets

        chain_details = f"[bold green]{chain_name}[/] ([dim]Chain ID: {chain_config_val.chainId}, RPC: {str(chain_config_val.rpcURL).rstrip('/')}[/])"
        chain_branch = tree.add(chain_details)

        if not markets_dict:
            chain_branch.add(
                "[dim italic]No data markets listed for this chain.[/dim italic]"
            )
            continue

        for market_name, market_config_val in sorted(markets_dict.items()):
            market_details_str = (
                f"[bold blue]{market_name}[/] - "
                f"Source: [yellow]{market_config_val.sourceChain}[/]"
            )
            market_branch_item = chain_branch.add(market_details_str)

            market_branch_item.add(
                f"[dim]Market Contract: {market_config_val.contractAddress}[/]"
            )
            market_branch_item.add(
                f"[dim]Market Protocol State: {market_config_val.powerloomProtocolStateContractAddress}[/]"
            )
            market_branch_item.add(f"[dim]Sequencer: {market_config_val.sequencer}[/]")
            market_branch_item.add(
                f"[dim]Compute: {str(market_config_val.compute.repo)} ({market_config_val.compute.branch}) Commit: {market_config_val.compute.commit[:7] if market_config_val.compute.commit else 'N/A'}[/]"
            )
            market_branch_item.add(
                f"[dim]Config: {str(market_config_val.config.repo)} ({market_config_val.config.branch}) Commit: {market_config_val.config.commit[:7] if market_config_val.config.commit else 'N/A'}[/]"
            )

    console.print("\n")
    console.print(tree)
    console.print("\n")


if __name__ == "__main__":
    app()
