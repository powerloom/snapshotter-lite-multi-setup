import os
from pathlib import Path
from typing import Dict, Optional

import psutil
import typer
from dotenv import dotenv_values
from rich.panel import Panel

from snapshotter_cli.utils.console import Prompt, console
from snapshotter_cli.utils.deployment import (
    CONFIG_DIR,
    CONFIG_ENV_FILENAME_TEMPLATE,
    calculate_connection_refresh_interval,
)
from snapshotter_cli.utils.models import CLIContext, MarketConfig, PowerloomChainConfig

ENV_FILENAME_TEMPLATE = ".env.{}.{}.{}"  # e.g. .env.devnet.uniswapv2.eth-mainnet


def parse_env_file_vars(file_path: str) -> Dict[str, str]:
    """Parses a .env file and returns a dictionary of key-value pairs."""
    env_vars = {}
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars


def get_default_env_vars() -> Dict[str, str]:
    """Loads default .env variables from env.example in the project root."""
    # Assuming env.example is in the parent directory of snapshotter_cli
    project_root = Path(__file__).resolve().parent.parent.parent
    env_example_path = project_root / "env.example"
    return parse_env_file_vars(str(env_example_path))


def configure_command(
    ctx: typer.Context,
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Profile name to use (default: 'default')"
    ),
    environment: Optional[str] = typer.Option(
        None, "--env", "-e", help="Powerloom chain name (e.g., DEVNET, MAINNET)"
    ),
    data_market: Optional[str] = typer.Option(
        None, "--market", "-m", help="Data market name (e.g., UNISWAPV2)"
    ),
    wallet_address: Optional[str] = typer.Option(
        None, "--wallet", "-w", help="Wallet address (0x...) holding the slots"
    ),
    signer_address: Optional[str] = typer.Option(
        None, "--signer", "-s", help="Signer account address (0x...)"
    ),
    signer_key: Optional[str] = typer.Option(
        None, "--signer-key", "-k", help="Signer account private key", hide_input=True
    ),
    source_rpc_url: Optional[str] = typer.Option(
        None, "--source-rpc", "-r", help="Source chain RPC URL"
    ),
    powerloom_rpc_url: Optional[str] = typer.Option(
        None, "--powerloom-rpc", "-p", help="Powerloom RPC URL"
    ),
    telegram_chat_id: Optional[str] = typer.Option(
        None, "--telegram-chat", "-t", help="Telegram chat ID for notifications"
    ),
    telegram_reporting_url: Optional[str] = typer.Option(
        "", "--telegram-url", "-u", help="Telegram reporting URL"
    ),
    telegram_thread_id: Optional[str] = typer.Option(
        None,
        "--telegram-thread",
        help="Telegram message thread ID for organizing notifications",
    ),
    max_stream_pool_size: Optional[int] = typer.Option(
        None,
        "--max-stream-pool-size",
        "-p",
        help="Max stream pool size for local collector",
    ),
    connection_refresh_interval: Optional[int] = typer.Option(
        None,
        "--connection-refresh-interval",
        "-c",
        help="Connection refresh interval for local collector to sequencer",
    ),
    local_collector_p2p_port: Optional[int] = typer.Option(
        None,
        "--local-collector-p2p-port",
        help="P2P port for local collector (gossipsub mesh communication, default: 8001)",
    ),
):
    """Configure credentials and settings for a specific chain and market combination."""
    cli_context: CLIContext = ctx.obj
    if not cli_context or not cli_context.chain_markets_map:
        console.print(
            "❌ Could not load markets configuration. Cannot proceed.", style="bold red"
        )
        raise typer.Exit(1)

    # --- Select Powerloom Chain ---
    selected_chain_name_upper: str
    if environment:
        selected_chain_name_upper = environment.upper()
        if selected_chain_name_upper not in cli_context.available_environments:
            console.print(
                f"❌ Invalid environment: {environment}. Valid: {', '.join(cli_context.available_environments)}",
                style="bold red",
            )
            raise typer.Exit(1)
    else:
        # Sort chains to prioritize MAINNET first
        chain_list = sorted(
            cli_context.available_environments,
            key=lambda x: (x.upper() != "MAINNET", x.upper()),
        )

        # Display chains in a panel like deployment command
        chain_list_display = "\n".join(
            f"[bold green]{i}.[/] [cyan]{chain.title()}[/]"
            for i, chain in enumerate(chain_list, 1)
        )
        panel = Panel(
            chain_list_display,
            title="[bold blue]Select Powerloom Chain[/]",
            border_style="blue",
            padding=(1, 2),
        )
        console.print(panel)

        while True:
            chain_input = Prompt.ask("👉 Select Powerloom chain (number or name)")
            if chain_input.isdigit():
                idx = int(chain_input) - 1
                if 0 <= idx < len(chain_list):
                    selected_chain_name_upper = chain_list[idx]
                    break
            elif chain_input.upper() in cli_context.available_environments:
                selected_chain_name_upper = chain_input.upper()
                break
            console.print("❌ Invalid selection. Please try again.", style="red")

    # --- Select Data Market ---
    chain_data = cli_context.chain_markets_map[selected_chain_name_upper]

    # --- Get Powerloom RPC URL from chain config (used as fallback) ---
    chain_config = chain_data.chain_config
    default_rpc_url = str(chain_config.rpcURL).rstrip("/")

    available_markets = sorted(chain_data.markets.keys())
    if not available_markets:
        console.print(
            f"❌ No data markets available for {selected_chain_name_upper}.",
            style="bold red",
        )
        raise typer.Exit(1)

    selected_market_name_upper: str
    if data_market:
        selected_market_name_upper = data_market.upper()
        if selected_market_name_upper not in available_markets:
            console.print(
                f"❌ Invalid market: {data_market}. Valid: {', '.join(available_markets)}",
                style="bold red",
            )
            raise typer.Exit(1)
    else:
        # Auto-select if only one market is available
        if len(available_markets) == 1:
            selected_market_name_upper = available_markets[0]
            console.print(
                f"✅ Auto-selected the only available market: [bold cyan]{selected_market_name_upper}[/bold cyan]",
                style="green",
            )
        else:
            # Multiple markets - show selection UI
            for i, market in enumerate(available_markets, 1):
                market_obj = chain_data.markets[market]
                console.print(
                    f"[bold green]{i}.[/] [cyan]{market}[/] ([dim]Source: {market_obj.sourceChain}[/])"
                )
            while True:
                market_input = Prompt.ask("👉 Select data market (number or name)")
                if market_input.isdigit():
                    idx = int(market_input) - 1
                    if 0 <= idx < len(available_markets):
                        selected_market_name_upper = available_markets[idx]
                        break
                elif market_input.upper() in available_markets:
                    selected_market_name_upper = market_input.upper()
                    break
                console.print("❌ Invalid selection. Please try again.", style="red")

    selected_market_obj = chain_data.markets[selected_market_name_upper]

    # --- Profile Support ---
    from snapshotter_cli.utils.profile import (
        ProfileConfig,
        ensure_profile_structure,
        get_active_profile,
        get_profile_env_path,
    )

    # Ensure profile structure exists (handles migration)
    ensure_profile_structure()

    # Determine active profile
    active_profile = get_active_profile(profile)

    if active_profile != "default":
        console.print(
            f"🏷️ Using profile: [bold magenta]{active_profile}[/bold magenta]",
            style="dim",
        )

    # Update last used profile
    profile_config = ProfileConfig()
    profile_config.set_last_used_profile(active_profile)

    # --- Create Namespaced .env File in Profile ---
    norm_chain_name = selected_chain_name_upper.lower()
    norm_market_name = selected_market_name_upper.lower()
    norm_source_chain = selected_market_obj.sourceChain.lower().replace("-", "_")

    # Get profile-specific env file path
    env_file_path = get_profile_env_path(
        active_profile, norm_chain_name, norm_market_name, norm_source_chain
    )

    # Ensure profile directory exists
    env_file_path.parent.mkdir(parents=True, exist_ok=True)

    # Check legacy locations for backward compatibility
    env_filename = CONFIG_ENV_FILENAME_TEMPLATE.format(
        norm_chain_name, norm_market_name, norm_source_chain
    )

    # Check old CONFIG_DIR location
    legacy_env_path = CONFIG_DIR / env_filename
    if legacy_env_path.exists() and active_profile == "default":
        console.print(
            f"⚠️ Found legacy env file. Migrating to profile structure...",
            style="yellow",
        )
        try:
            import shutil

            shutil.move(str(legacy_env_path), str(env_file_path))
            console.print(
                f"✓ Migrated configuration to profile '{active_profile}'", style="dim"
            )
        except OSError as e:
            console.print(f"⚠️ Could not migrate legacy file: {e}", style="yellow")

    # Load existing env file values if it exists
    existing_env_vars = {}
    if env_file_path.exists():
        existing_env_vars = dotenv_values(env_file_path)
        console.print(
            f"ℹ️ Existing configuration found for {env_filename}. Using existing values as defaults.",
            style="yellow",
        )

    # Calculate recommended max stream pool size based on CPU count
    cpus = psutil.cpu_count(logical=True)
    if cpus >= 2 and cpus < 4:
        recommended_max_stream_pool_size = 40
    elif cpus >= 4:
        recommended_max_stream_pool_size = 100
    else:
        recommended_max_stream_pool_size = 20
    # --- Collect Credentials ---
    final_wallet_address = wallet_address or Prompt.ask(
        "👉 Enter slot NFT holder wallet address (0x...)",
        default=existing_env_vars.get("WALLET_HOLDER_ADDRESS", ""),
    )
    final_signer_address = signer_address or Prompt.ask(
        "👉 Enter SNAPSHOTTER signer address (0x...)",
        default=existing_env_vars.get("SIGNER_ACCOUNT_ADDRESS", ""),
    )
    final_signer_key = signer_key
    if not final_signer_key:
        existing_key = existing_env_vars.get("SIGNER_ACCOUNT_PRIVATE_KEY", "")
        final_signer_key = Prompt.ask(
            "👉 Enter signer private key",
            password=True,
            default="(hidden)" if existing_key else "",
        )
        if final_signer_key == "(hidden)" or final_signer_key == "":
            final_signer_key = existing_key

    final_source_rpc = source_rpc_url or Prompt.ask(
        f"👉 Enter RPC URL for {selected_market_obj.sourceChain}",
        default=existing_env_vars.get("SOURCE_RPC_URL", ""),
    )
    # Prompt for Powerloom RPC URL (existing env takes precedence over chain default)
    if powerloom_rpc_url:
        final_powerloom_rpc_url = powerloom_rpc_url
        console.print(
            f"✅ Using Powerloom RPC URL from CLI: [bold cyan]{final_powerloom_rpc_url}[/bold cyan]",
            style="green",
        )
    else:
        existing_powerloom_rpc = existing_env_vars.get("POWERLOOM_RPC_URL", "").strip()
        final_powerloom_rpc_url = Prompt.ask(
            "👉 Enter Powerloom RPC URL",
            default=existing_powerloom_rpc or default_rpc_url,
        )
    final_telegram_chat = telegram_chat_id or Prompt.ask(
        "👉 Enter Telegram chat ID (optional)",
        default=existing_env_vars.get("TELEGRAM_CHAT_ID", ""),
    )
    # Don't prompt for Telegram reporting URL - use existing or default
    final_telegram_url = (
        telegram_reporting_url
        or existing_env_vars.get("TELEGRAM_REPORTING_URL")
        or "https://tg-testing.powerloom.io/"
    )

    # Prompt for Telegram notification cooldown and thread ID only if chat ID is provided
    final_telegram_cooldown = ""
    final_telegram_thread = ""
    if final_telegram_chat:
        default_cooldown = existing_env_vars.get(
            "TELEGRAM_NOTIFICATION_COOLDOWN", "300"
        )
        final_telegram_cooldown = Prompt.ask(
            "👉 Enter Telegram notification cooldown in seconds (optional)",
            default=default_cooldown,
        )

        # Prompt for Telegram thread ID
        final_telegram_thread = telegram_thread_id or Prompt.ask(
            "👉 Enter Telegram message thread ID for organizing notifications (optional, leave empty for main chat)",
            default=existing_env_vars.get("TELEGRAM_MESSAGE_THREAD_ID", ""),
        )

    # Don't prompt for max stream pool size - use existing or recommended value
    final_max_stream_pool_size = (
        max_stream_pool_size
        or existing_env_vars.get("MAX_STREAM_POOL_SIZE")
        or str(recommended_max_stream_pool_size)
    )

    # Ensure it doesn't exceed recommended value
    if int(final_max_stream_pool_size) > recommended_max_stream_pool_size:
        console.print(
            f"⚠️ MAX_STREAM_POOL_SIZE ({final_max_stream_pool_size}) is greater than the recommended {recommended_max_stream_pool_size} for {cpus} logical CPUs, using recommended value.",
            style="yellow",
        )
        final_max_stream_pool_size = str(recommended_max_stream_pool_size)

    # Don't prompt for connection refresh interval - use existing or 60 seconds
    final_connection_refresh_interval = (
        connection_refresh_interval
        or existing_env_vars.get("CONNECTION_REFRESH_INTERVAL_SEC")
        or "60"
    )

    # Prompt for LOCAL_COLLECTOR_P2P_PORT (important for decentralized gossipsub mesh).
    # If the namespaced env did not have this key earlier, default "8001" is shown and written on save.
    final_local_collector_p2p_port = (
        str(local_collector_p2p_port)
        if local_collector_p2p_port is not None
        else Prompt.ask(
            "👉 Enter local collector P2P port (for gossipsub mesh communication)",
            default=existing_env_vars.get("LOCAL_COLLECTOR_P2P_PORT", "8001"),
        )
    )
    
    # Start with all existing env vars to preserve any that aren't part of the template
    # This prevents overwriting custom env vars like LOCAL_COLLECTOR_HEALTH_CHECK_PORT
    # Filter out None values (dotenv_values returns None for missing keys)
    final_env_vars = {
        k: v for k, v in (existing_env_vars.items() if existing_env_vars else {})
        if v is not None
    }
    
    # Update only the configured fields (merge approach)
    if final_wallet_address:
        final_env_vars["WALLET_HOLDER_ADDRESS"] = final_wallet_address
    if final_signer_address:
        final_env_vars["SIGNER_ACCOUNT_ADDRESS"] = final_signer_address
    if final_signer_key:
        final_env_vars["SIGNER_ACCOUNT_PRIVATE_KEY"] = final_signer_key
    if final_source_rpc:
        final_env_vars["SOURCE_RPC_URL"] = final_source_rpc
    if final_telegram_chat:
        final_env_vars["TELEGRAM_CHAT_ID"] = final_telegram_chat
    if final_telegram_url:
        final_env_vars["TELEGRAM_REPORTING_URL"] = final_telegram_url
    if final_telegram_cooldown:
        final_env_vars["TELEGRAM_NOTIFICATION_COOLDOWN"] = final_telegram_cooldown
    if final_telegram_thread:
        final_env_vars["TELEGRAM_MESSAGE_THREAD_ID"] = final_telegram_thread
    if final_max_stream_pool_size:
        final_env_vars["MAX_STREAM_POOL_SIZE"] = final_max_stream_pool_size
    if final_connection_refresh_interval:
        final_env_vars["CONNECTION_REFRESH_INTERVAL_SEC"] = final_connection_refresh_interval
    if final_powerloom_rpc_url:
        final_env_vars["POWERLOOM_RPC_URL"] = final_powerloom_rpc_url
    if final_local_collector_p2p_port:
        final_env_vars["LOCAL_COLLECTOR_P2P_PORT"] = final_local_collector_p2p_port

    # Set default values for LITE_NODE_BRANCH and LOCAL_COLLECTOR_IMAGE_TAG if not present
    final_env_vars.setdefault("LITE_NODE_BRANCH", "main")
    final_env_vars.setdefault("LOCAL_COLLECTOR_IMAGE_TAG", "latest")
    
    # Build env_contents list from the merged dict for display and writing
    env_contents = []
    # Define the order for template fields (for consistent output)
    template_field_order = [
        "WALLET_HOLDER_ADDRESS",
        "SIGNER_ACCOUNT_ADDRESS",
        "SIGNER_ACCOUNT_PRIVATE_KEY",
        "SOURCE_RPC_URL",
        "POWERLOOM_RPC_URL",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_REPORTING_URL",
        "TELEGRAM_NOTIFICATION_COOLDOWN",
        "TELEGRAM_MESSAGE_THREAD_ID",
        "MAX_STREAM_POOL_SIZE",
        "CONNECTION_REFRESH_INTERVAL_SEC",
        "LOCAL_COLLECTOR_P2P_PORT",
        "LITE_NODE_BRANCH",
        "LOCAL_COLLECTOR_IMAGE_TAG",
    ]
    
    # Add template fields in order
    for key in template_field_order:
        if key in final_env_vars and final_env_vars[key] is not None:
            env_contents.append(f"{key}={final_env_vars[key]}")
    
    # Add any remaining env vars that aren't in the template (preserve custom vars)
    for key, value in sorted(final_env_vars.items()):
        if key not in template_field_order and value is not None:
            env_contents.append(f"{key}={value}")

    if env_file_path.exists():
        while True:
            response = (
                Prompt.ask(
                    f"⚠️ {env_filename} already exists. Overwrite? [y/N]", default="n"
                )
                .lower()
                .strip()
            )

            if response in ["y", "yes"]:
                break  # Proceed with overwrite
            elif response in ["n", "no", ""]:
                console.print("❌ Aborted.", style="yellow")
                raise typer.Exit(1)
            else:
                console.print(
                    "❌ Invalid input. Please enter 'y' for yes or 'n' for no.",
                    style="red",
                )

    try:
        with open(env_file_path, "w") as f:
            f.write("\n".join(env_contents))
        console.print(
            f"✅ Created {env_file_path} with following values:", style="bold green"
        )
        panel_content = []
        for line in env_contents:
            if "SIGNER_ACCOUNT_PRIVATE_KEY" in line:
                panel_content.append("SIGNER_ACCOUNT_PRIVATE_KEY=(hidden)")
            else:
                panel_content.append(line)
        panel = Panel(
            "\n".join(panel_content),
            title="Environment File Contents",
            border_style="cyan",
        )
        console.print(panel)
    except Exception as e:
        console.print(f"❌ Error writing {env_file_path}: {e}", style="bold red")
        raise typer.Exit(1)
