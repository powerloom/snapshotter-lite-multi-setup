import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

import typer
from rich.panel import Panel

from snapshotter_cli.utils.console import Prompt, console
from snapshotter_cli.utils.config_helpers import get_credential
from snapshotter_cli.utils.deployment import (
    CONFIG_DIR,
    CONFIG_ENV_FILENAME_TEMPLATE,
    parse_env_file_vars,
    run_git_command,
)
from snapshotter_cli.utils.deployment import run_os_system_command
from snapshotter_cli.utils.models import CLIContext
from snapshotter_cli.utils.system_checks import is_docker_running
from snapshotter_cli.utils.system_checks import does_screen_session_exist

# Constants for monitor service - UPDATED
MONITOR_SERVICE_REPO_URL = "git@github.com:powerloom/submissions-monitor-alerts.git"
MONITOR_SERVICE_DIR = Path("submissions-monitor-alerts")
MONITOR_ENV_FILENAME_TEMPLATE = ".env.monitor.{}.{}"  # e.g. .env.monitor.devnet.uniswapv2

# Create monitor app with subcommands
monitor_app = typer.Typer(help="Monitor slot submission services")


def cleanup_monitor_containers(chain_name: str):
    """Clean up any running monitor containers for the given chain."""
    try:
        norm_chain_name = chain_name.lower()
        container_name = f"powerloom-active-node-monitor-{norm_chain_name}"
        
        console.print(f"  🧹 Cleaning up monitor containers for {chain_name}...", style="dim")
        
        # Stop and remove the container if it exists
        result = subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode == 0:
            console.print(f"    ✅ Stopped container: {container_name}", style="dim")
        
        result = subprocess.run(
            ["docker", "rm", container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode == 0:
            console.print(f"    ✅ Removed container: {container_name}", style="dim")
        
        # Also try to remove any related images
        result = subprocess.run(
            ["docker", "rmi", "powerloom-active-node-monitor:latest"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        console.print(f"  ✅ Monitor container cleanup completed for {chain_name}", style="dim")
        
    except Exception as e:
        console.print(f"  ⚠️ Warning: Could not cleanup containers: {e}", style="yellow")


def deploy_monitor_service(
    powerloom_chain_name: str,
    wallet_address: str,
    webhook_url: str,
    webhook_service: str = "slack",
    slots_to_ignore: Optional[List[int]] = None,
    base_monitor_repo_path: Path = None,
    chain_config=None,
    market_config=None,
) -> bool:
    """
    Deploys the slot submission monitoring service for a given chain and wallet.
    Returns True on success, False on failure.
    """
    console.print(
        f"🔍 Starting monitor deployment for Powerloom Chain [bold magenta]{powerloom_chain_name}[/bold magenta], Wallet [bold blue]{wallet_address}[/bold blue]",
        style="green",
    )

    # 1. Determine Paths
    norm_pl_chain_name = powerloom_chain_name.lower()
    monitor_instance_dir = Path(os.getcwd()) / MONITOR_SERVICE_DIR / norm_pl_chain_name
    env_file_path = monitor_instance_dir / ".env"

    console.print(f"  📂 Monitor directory: {monitor_instance_dir}")

    if monitor_instance_dir.exists():
        console.print(
            f"  ⚠️ Monitor directory {monitor_instance_dir} already exists. Removing for a fresh deployment.",
            style="yellow",
        )
        try:
            shutil.rmtree(monitor_instance_dir)
        except OSError as e:
            console.print(
                f"  ❌ Could not remove existing directory {monitor_instance_dir}: {e}",
                style="bold red",
            )
            return False

    try:
        monitor_instance_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"  📂 Created monitor directory: {monitor_instance_dir}", style="dim")
    except OSError as e:
        console.print(
            f"  ❌ Could not create monitor directory {monitor_instance_dir}: {e}",
            style="bold red",
        )
        return False

    # 2. Copy from base monitor service clone
    if base_monitor_repo_path and base_monitor_repo_path.exists():
        console.print(
            f"  📂 Copying base monitor service from {base_monitor_repo_path} to {monitor_instance_dir}",
            style="dim",
        )
        console.print(f"  📂 Monitor instance directory exists: {monitor_instance_dir.exists()}", style="dim")
        console.print(f"  📂 Monitor instance directory absolute path: {monitor_instance_dir.absolute()}", style="dim")
        try:
            # Copy contents of base_monitor_repo_path to monitor_instance_dir
            # Use the same approach as deployment.py
            console.print(f"  📂 Base repo path exists: {base_monitor_repo_path.exists()}", style="dim")
            console.print(f"  📂 Base repo contents:", style="dim")
            for item in base_monitor_repo_path.iterdir():
                console.print(f"    - {item.name}", style="dim")
            
            # Use the exact same pattern as deployment.py
            try:
                shutil.copytree(
                    base_monitor_repo_path, monitor_instance_dir, dirs_exist_ok=True
                )
            except Exception as copy_error:
                console.print(f"  ❌ Copy error: {copy_error}", style="bold red")
                console.print(f"  📂 Source exists: {base_monitor_repo_path.exists()}", style="dim")
                console.print(f"  📂 Destination exists: {monitor_instance_dir.exists()}", style="dim")
                raise copy_error
            console.print(
                f"    ✅ Base monitor service copied successfully.", style="dim green"
            )
            # Debug: List files in the monitor instance directory
            console.print(f"    📂 Monitor instance directory exists after copy: {monitor_instance_dir.exists()}", style="dim")
            console.print(f"    📂 Files in {monitor_instance_dir}:", style="dim")
            if monitor_instance_dir.exists():
                for item in monitor_instance_dir.iterdir():
                    console.print(f"      - {item.name}", style="dim")
            else:
                console.print(f"      ❌ Directory does not exist!", style="red")
        except Exception as e:
            console.print(
                f"  ❌ Error copying base monitor service files from {base_monitor_repo_path} to {monitor_instance_dir}: {e}",
                style="bold red",
            )
            return False
    else:
        # Clone directly if no base repo provided
        console.print(
            f"  📂 Cloning monitor service from {MONITOR_SERVICE_REPO_URL}",
            style="dim",
        )
        if not run_git_command(
            ["git", "clone", MONITOR_SERVICE_REPO_URL, "."],
            cwd=monitor_instance_dir,
            desc=f"Cloning monitor service from {MONITOR_SERVICE_REPO_URL}",
        ):
            console.print(
                f"❌ Failed to clone monitor service from {MONITOR_SERVICE_REPO_URL}.",
                style="bold red",
            )
            return False

    # 3. Generate .env file for monitor service
    final_env_vars: Dict[str, str] = {}

    # 1. Load from pre-configured namespaced .env file (if exists)
    # This forms the base. User can put any specific overrides here.
    norm_pl_chain_name_for_file = powerloom_chain_name.lower()
    norm_market_name_for_file = market_config.name.lower() if market_config else ""
    norm_source_chain_name_for_file = market_config.sourceChain.lower().replace("-", "_") if market_config else ""

    potential_config_filename = CONFIG_ENV_FILENAME_TEMPLATE.format(
        norm_pl_chain_name_for_file,
        norm_market_name_for_file,
        norm_source_chain_name_for_file,
    )

    # First check in config directory
    config_file_path = CONFIG_DIR / potential_config_filename
    if config_file_path.exists():
        console.print(
            f"  ℹ️ Found pre-configured .env template in config directory: {config_file_path}. Loading it.",
            style="dim",
        )
        final_env_vars.update(parse_env_file_vars(str(config_file_path)))
    else:
        # Check current directory for backward compatibility
        cwd_config_file_path = Path(os.getcwd()) / potential_config_filename
        if cwd_config_file_path.exists():
            console.print(
                f"  ⚠️ Found legacy env file in current directory: {cwd_config_file_path}. Consider moving it to {CONFIG_DIR}",
                style="yellow",
            )
            final_env_vars.update(parse_env_file_vars(str(cwd_config_file_path)))
        else:
            console.print(
                f"  ℹ️ No pre-configured .env template found. Using minimal core settings.",
                style="dim",
            )

    # 2. Copy env.example and only modify what's necessary
    env_example_path = base_monitor_repo_path / "env.example"
    if not env_example_path.exists():
        console.print(
            f"  ❌ env.example not found at {env_example_path}", style="bold red"
        )
        return False
    
    # Read the env.example file
    try:
        with open(env_example_path, "r") as f:
            env_content = f.read()
    except IOError as e:
        console.print(
            f"  ❌ Error reading env.example: {e}", style="bold red"
        )
        return False
    
    # Replace only the specific values we need to set
    replacements = {
        "ANCHOR_CHAIN__CHAIN_ID=": f"ANCHOR_CHAIN__CHAIN_ID={chain_config.chainId if chain_config else ''}",
        "ANCHOR_CHAIN__RPC__FULL_NODES__0__URL=": f"ANCHOR_CHAIN__RPC__FULL_NODES__0__URL={str(chain_config.rpcURL).rstrip('/') if chain_config else ''}",
        "PROTOCOL_STATE_ADDRESS=": f"PROTOCOL_STATE_ADDRESS={market_config.powerloomProtocolStateContractAddress if market_config else ''}",
        "DATA_MARKET_ADDRESS=": f"DATA_MARKET_ADDRESS={market_config.contractAddress if market_config else ''}",
        "NETWORK=": f"NETWORK={powerloom_chain_name.lower()}",
        "WALLET_HOLDER_ADDRESS=": f"WALLET_HOLDER_ADDRESS={wallet_address}",
        "SLOTS_TO_IGNORE=": f"SLOTS_TO_IGNORE={','.join(map(str, slots_to_ignore)) if slots_to_ignore else '[]'}",
        "WEBHOOK__SERVICE=": f"WEBHOOK__SERVICE={webhook_service}",
        "WEBHOOK__URL=": f"WEBHOOK__URL={webhook_url}",
    }
    
    # Apply replacements - process line by line to avoid duplicates
    lines = env_content.split('\n')
    processed_lines = []
    
    for line in lines:
        # Check if this line needs to be replaced
        replaced = False
        for old_line, new_line in replacements.items():
            if line.strip().startswith(old_line):
                processed_lines.append(new_line)
                replaced = True
                break
        
        if not replaced:
            processed_lines.append(line)
    
    env_content = '\n'.join(processed_lines)

    try:
        with open(env_file_path, "w") as f:
            f.write(f"# Auto-generated .env for monitor service on {powerloom_chain_name}\n")
            f.write(f"# Deployment Path: {monitor_instance_dir}\n\n")
            f.write(env_content)
        console.print(f"  📄 Generated .env file: {env_file_path}", style="dim green")
    except IOError as e:
        console.print(
            f"  ❌ Error writing .env file {env_file_path}: {e}", style="bold red"
        )
        return False

    # 4. Run the build script
    console.print(
        f"  🚀 Running build script for monitor service...",
        style="dim blue",
    )

    # Change current working directory to monitor_instance_dir
    original_cwd = Path(os.getcwd())
    try:
        # Verify the directory exists before changing to it
        console.print(f"  📂 Current working directory: {os.getcwd()}", style="dim")
        console.print(f"  📂 Monitor instance directory absolute: {monitor_instance_dir.absolute()}", style="dim")
        console.print(f"  📂 Monitor instance directory exists: {monitor_instance_dir.exists()}", style="dim")
        
        if not monitor_instance_dir.exists():
            console.print(
                f"  ❌ Monitor instance directory {monitor_instance_dir} does not exist.",
                style="bold red",
            )
            return False
        
        console.print(f"  📂 Changing to directory: {monitor_instance_dir}", style="dim")
        console.print(f"  📂 Current working directory before change: {os.getcwd()}", style="dim")
        console.print(f"  📂 Target directory absolute: {monitor_instance_dir.absolute()}", style="dim")
        console.print(f"  📂 Target directory exists: {monitor_instance_dir.exists()}", style="dim")
        os.chdir(monitor_instance_dir)
        console.print(f"  📂 Current working directory after change: {os.getcwd()}", style="dim")

        # Make build.sh executable
        build_sh_path = Path("build.sh")
        console.print(f"  📂 Build script path: {build_sh_path.absolute()}", style="dim")
        console.print(f"  📂 Build script exists: {build_sh_path.exists()}", style="dim")
        if build_sh_path.exists():
            os.chmod(build_sh_path, 0o755)
            console.print(f"  📂 Made build script executable", style="dim")

        # --- Spawning monitor service using screen and build.sh ---
        console.print(
            f"  🚀 Spawning monitor service for {powerloom_chain_name} via screen and build.sh...",
            style="dim blue",
        )

        # Use a screen name based on the monitor instance structure
        screen_session_name = f"pl_monitor_{norm_pl_chain_name}"

        
        if does_screen_session_exist(screen_session_name):
            console.print(
                f"  ❌ Error: Screen session named '{screen_session_name}' already exists.",
                style="bold red",
            )
            console.print(
                f"     Please clean it up manually (e.g., using 'screen -X -S {screen_session_name} quit' or 'screen -wipe') and try again.",
                style="yellow",
            )
            return False

        # Create screen session
        screen_create_cmd = f"screen -dmS {screen_session_name}"
        if not run_os_system_command(
            screen_create_cmd, screen_session_name, "Create screen session"
        ):
            return False

        # Send build command to screen session
        build_command_to_stuff = f"./build.sh --slot-monitor --skip\n"
        screen_stuff_cmd = (
            f'screen -r {screen_session_name} -p 0 -X stuff "{build_command_to_stuff}"'
        )

        if not run_os_system_command(
            screen_stuff_cmd, screen_session_name, "Send build.sh command"
        ):
            run_os_system_command(
                f"screen -X -S {screen_session_name} quit",
                screen_session_name,
                "Quit screen session on error",
            )
            return False

        console.print(
            f"    ✅ Monitor service for {powerloom_chain_name} launched in screen session: {screen_session_name}",
            style="green",
        )

        # Sleep to allow service to start
        sleep_duration = 10
        console.print(
            f"    ⏳ Sleeping for {sleep_duration} seconds to allow service to initialize...",
            style="dim",
        )
        time.sleep(sleep_duration)

    except subprocess.TimeoutExpired as e:
        console.print(
            f"  ❌ Build script timed out after 60 seconds: {e}", style="bold red"
        )
        # Cleanup containers if build fails
        cleanup_monitor_containers(powerloom_chain_name)
        return False
    except Exception as e:
        console.print(
            f"  ❌ Exception during monitor service build: {e}", style="bold red"
        )
        # Cleanup containers if build fails
        cleanup_monitor_containers(powerloom_chain_name)
        return False
    finally:
        os.chdir(original_cwd)  # Always restore CWD

    console.print(
        f"✅ Monitor service deployment for [bold magenta]{powerloom_chain_name}[/bold magenta] completed successfully.",
        style="bold green",
    )
    
    # Provide helpful management commands
    console.print(f"\n📋 Service Management Commands:", style="bold blue")
    console.print(f"  • View screen session: screen -r pl_monitor_{norm_pl_chain_name}", style="dim")
    console.print(f"  • List screen sessions: screen -ls", style="dim")
    console.print(f"  • View logs: cd {monitor_instance_dir} && docker-compose logs -f", style="dim")
    console.print(f"  • Check status: cd {monitor_instance_dir} && docker-compose ps", style="dim")
    
    return True


@monitor_app.command("stop")
def monitor_stop_command():
    """Stop all running monitor services."""
    stop_monitor_services()


@monitor_app.command("clean")
def monitor_clean_command():
    """Remove all monitor configurations with confirmation."""
    clean_monitor_configurations()


def list_monitor_screen_sessions() -> list[dict[str, str]]:
    """Lists running screen sessions matching the monitor naming convention."""
    sessions = []
    try:
        process = subprocess.run(
            ["screen", "-ls"], capture_output=True, text=True, check=False, timeout=5
        )
        if (
            process.returncode > 1
            and "No Sockets found" not in process.stdout
            and "No Sockets found" not in process.stderr
        ):
            console.print(
                f"[dim]Error running 'screen -ls'. RC: {process.returncode}, Stderr: {process.stderr.strip()}[/dim]",
                style="yellow",
            )
            return sessions

        for line in process.stdout.splitlines():
            line = line.strip()
            parts = line.split("\t")
            if not parts or len(parts) < 2:  # Need at least name and status part
                continue

            pid_session_part = parts[0]
            status_part = parts[1]  # e.g., (01/23/2024 11:29:09 AM)   (Detached)

            if "." in pid_session_part:
                pid_str, session_name = pid_session_part.split(".", 1)
                # Check if it matches our monitor naming convention: pl_monitor_{chain}
                if session_name.startswith("pl_monitor_"):
                    sessions.append(
                        {
                            "pid": pid_str,
                            "name": session_name,
                            "status_str": status_part.strip(),
                        }
                    )
        return sessions
    except FileNotFoundError:
        console.print(
            "❌ 'screen' command not found. Is screen installed?", style="red"
        )
        return sessions
    except subprocess.TimeoutExpired:
        console.print("⏰ Timeout while running 'screen -ls'.", style="yellow")
        return sessions
    except Exception as e:
        console.print(
            f"⚠️ Unexpected error while listing monitor screen sessions: {e}", style="yellow"
        )
        return sessions


def stop_monitor_services():
    """Stop all running monitor services."""
    # Find all monitor screen sessions
    monitor_sessions = list_monitor_screen_sessions()
    
    if not monitor_sessions:
        console.print("ℹ️ No running monitor services found.", style="yellow")
        return True
    
    console.print(f"📋 Found {len(monitor_sessions)} running monitor service(s):", style="blue")
    for session in monitor_sessions:
        console.print(f"  • {session['name']} (PID: {session['pid']}) - {session['status_str']}", style="dim")
    
    # Prompt for confirmation (following diagnose.py pattern)
    if typer.confirm("Would you like to stop all monitor services?"):
        console.print("Stopping monitor services...", style="yellow")
        
        # Stop each session
        for session in monitor_sessions:
            try:
                session_name = session["name"]
                session_pid = session["pid"]
                
                # Stop the screen session
                subprocess.run(
                    ["screen", "-X", "-S", session_name, "quit"], 
                    capture_output=True, 
                    check=True
                )
                console.print(
                    f"✅ Stopped monitor service: {session_name} ({session_pid})",
                    style="green",
                )
            except subprocess.CalledProcessError as e:
                console.print(
                    f"⚠️ Failed to stop monitor service {session_name} ({session_pid}): {e}",
                    style="red",
                )
                continue
        
        console.print("Monitor service cleanup completed", style="green")
    else:
        console.print("❌ Operation cancelled.", style="yellow")
        return False
    
    return True


def clean_monitor_configurations():
    """Remove all monitor configurations with confirmation."""
    # Find all monitor directories
    monitor_base_dir = Path(os.getcwd()) / MONITOR_SERVICE_DIR
    if not monitor_base_dir.exists():
        console.print("ℹ️ No monitor configurations found.", style="yellow")
        return True
    
    monitor_dirs = []
    for item in monitor_base_dir.iterdir():
        if item.is_dir():
            monitor_dirs.append(item)
    
    if not monitor_dirs:
        console.print("ℹ️ No monitor configurations found.", style="yellow")
        return True
    
    console.print(f"📋 Found {len(monitor_dirs)} monitor configuration(s):", style="blue")
    for monitor_dir in monitor_dirs:
        console.print(f"  • {monitor_dir.name}", style="dim")
    
    # Prompt for confirmation (following diagnose.py pattern)
    if typer.confirm("Would you like to remove all monitor configurations? This will delete all monitor data."):
        console.print("Removing monitor configurations...", style="yellow")
        
        # Remove each directory
        for monitor_dir in monitor_dirs:
            try:
                shutil.rmtree(monitor_dir)
                console.print(
                    f"✅ Removed monitor configuration: {monitor_dir.name}",
                    style="green",
                )
            except Exception as e:
                console.print(
                    f"⚠️ Failed to remove monitor configuration {monitor_dir.name}: {e}",
                    style="red",
                )
                continue
        
        console.print("Monitor configuration cleanup completed", style="green")
    else:
        console.print("❌ Operation cancelled.", style="yellow")
        return False
    
    return True


@monitor_app.command("deploy")
def monitor_deploy_command(
    ctx: typer.Context,
    environment: Optional[str] = typer.Option(
        None,
        "--env",
        "-e",
        help="Deployment environment (Powerloom chain name). If not provided, you will be prompted.",
    ),
    wallet_address_opt: Optional[str] = typer.Option(
        None, "--wallet", "-w", help="Wallet address (0x...) to monitor."
    ),
    webhook_url_opt: Optional[str] = typer.Option(
        None, "--webhook-url", help="Webhook URL for notifications."
    ),
    webhook_service_opt: Optional[str] = typer.Option(
        None, "--webhook-service", help="Webhook service type (slack, discord, etc.)"
    ),
    slots_to_ignore_opt: Optional[str] = typer.Option(
        None, "--slots-to-ignore", help="Comma-separated list of slot IDs to ignore"
    ),
):
    """Deploy slot submission monitoring service for specified environment and wallet."""
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

    base_monitor_clone_path = Path(os.getcwd()) / ".tmp_monitor_base_clone"

    try:
        # --- Environment Selection ---
        if environment:
            selected_powerloom_chain_name_upper = environment.upper()
            if selected_powerloom_chain_name_upper not in cli_context.available_environments:
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
                title="[bold blue]Select Powerloom Chain for Monitor Deployment[/]",
                border_style="blue",
                padding=(1, 2),
            )
            console.print(panel)
            selected_chain_input = typer.prompt(
                "👉🏼 Select a Powerloom chain (number or name)", type=str
            )

            temp_chain_config_obj = None
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

        console.print(
            f"🔍 Deploying monitor for environment: [bold magenta]{selected_powerloom_chain_name_upper}[/bold magenta]...",
            style="bold green",
        )

        # --- Market Selection ---
        chain_data = cli_context.chain_markets_map.get(selected_powerloom_chain_name_upper)
        if not chain_data or not chain_data.markets:
            console.print(
                f"❌ No data markets found for {selected_powerloom_chain_name_upper} in sources.json.",
                style="bold red",
            )
            raise typer.Exit(1)

        available_market_names_on_chain = list(chain_data.markets.keys())
        selected_market_name_upper: str

        # Auto-select if only one market is available
        if len(available_market_names_on_chain) == 1:
            selected_market_name_upper = available_market_names_on_chain[0]
            console.print(
                f"✅ Auto-selected the only available market: [bold cyan]{selected_market_name_upper}[/bold cyan]",
                style="green",
            )
        else:
            # Multiple markets available - show selection UI
            market_lines = []
            for i, name in enumerate(available_market_names_on_chain):
                market_lines.append(
                    f"[bold green]{i+1}.[/] [cyan]{name}[/] ([dim]Source: {chain_data.markets[name].sourceChain}[/])"
                )

            market_display_list = "\n".join(market_lines)
            market_panel = Panel(
                market_display_list,
                title=f"[bold blue]Select Data Market on {selected_powerloom_chain_name_upper}[/]",
                border_style="blue",
                padding=(1, 2),
            )
            console.print(market_panel)

            # Interactive selection
            while True:
                selection = Prompt.ask(
                    "👉 Select market (number or name)",
                    default="1",
                )

                if selection.isdigit():
                    index = int(selection) - 1
                    if 0 <= index < len(available_market_names_on_chain):
                        selected_market_name_upper = available_market_names_on_chain[index]
                        break
                elif selection.upper() in available_market_names_on_chain:
                    selected_market_name_upper = selection.upper()
                    break
                console.print("❌ Invalid selection. Please try again.", style="red")

        selected_market_obj = chain_data.markets[selected_market_name_upper]
        console.print(
            f"✅ Selected market: [bold cyan]{selected_market_name_upper}[/bold cyan] on [bold yellow]{selected_market_obj.sourceChain}[/bold yellow]",
            style="green",
        )

        # --- Load market-specific namespaced .env file ---
        namespaced_env_content: Optional[Dict[str, str]] = None
        norm_pl_chain_name_for_file = selected_powerloom_chain_name_upper.lower()

        # Try to find any market config for this chain to use for env loading
        chain_data = cli_context.chain_markets_map.get(selected_powerloom_chain_name_upper)
        if chain_data and chain_data.markets:
            # Use the first available market for loading env file
            first_market_name = next(iter(chain_data.markets.keys()))
            market_obj = chain_data.markets[first_market_name]
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

        # --- Resolve Wallet Address ---
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

        # --- Resolve Webhook Configuration ---
        final_webhook_url = webhook_url_opt
        if not final_webhook_url:
            final_webhook_url = Prompt.ask(
                "👉 Enter webhook URL for notifications (e.g., Slack webhook URL)"
            )

        final_webhook_service = webhook_service_opt or Prompt.ask(
            "👉 Enter webhook service type",
            default="slack",
            choices=["slack", "discord", "teams", "custom"]
        )

        # --- Resolve Slots to Ignore ---
        slots_to_ignore: Optional[List[int]] = None
        if slots_to_ignore_opt:
            try:
                slots_to_ignore = [int(s.strip()) for s in slots_to_ignore_opt.split(",") if s.strip()]
            except ValueError:
                console.print(
                    "❌ Invalid slots-to-ignore format. Please use comma-separated numbers (e.g., 1,2,3)",
                    style="bold red",
                )
                raise typer.Exit(1)
        else:
            ignore_slots_input = Prompt.ask(
                "👉 Enter slot IDs to ignore (comma-separated, optional)",
                default=""
            )
            if ignore_slots_input.strip():
                try:
                    slots_to_ignore = [int(s.strip()) for s in ignore_slots_input.split(",") if s.strip()]
                except ValueError:
                    console.print(
                        "❌ Invalid slots format. Please use comma-separated numbers (e.g., 1,2,3)",
                        style="bold red",
                    )
                    raise typer.Exit(1)

        # --- Prepare Base Monitor Clone ---
        console.print(
            f"🛠️ Preparing base monitor service clone at {base_monitor_clone_path}...",
            style="blue",
        )
        if base_monitor_clone_path.exists():
            console.print(
                f"  🗑️ Removing existing temporary clone directory: {base_monitor_clone_path}",
                style="dim",
            )
            try:
                shutil.rmtree(base_monitor_clone_path)
            except OSError as e:
                console.print(
                    f"  ❌ Could not remove existing temporary clone directory {base_monitor_clone_path}: {e}",
                    style="bold red",
                )
                raise typer.Exit(1)

        try:
            base_monitor_clone_path.mkdir(
                parents=True, exist_ok=False
            )  # exist_ok=False to ensure it was just created
        except OSError as e:
            console.print(
                f"  ❌ Could not create temporary clone directory {base_monitor_clone_path}: {e}",
                style="bold red",
            )
            raise typer.Exit(1)

        git_result = run_git_command(
            ["git", "clone", MONITOR_SERVICE_REPO_URL, "."],
            cwd=base_monitor_clone_path,
            desc=f"Cloning monitor service from {MONITOR_SERVICE_REPO_URL}",
        )
        console.print(f"  📂 Git clone result: {git_result}", style="dim")
        
        if not git_result:
            console.print(
                f"❌ Failed to clone monitor service from {MONITOR_SERVICE_REPO_URL}.",
                style="bold red",
            )
            # Cleanup already created directory before exiting
            if base_monitor_clone_path.exists():
                shutil.rmtree(base_monitor_clone_path)
            raise typer.Exit(1)
        
        # Verify the clone actually worked
        if not base_monitor_clone_path.exists():
            console.print(
                f"❌ Base clone directory {base_monitor_clone_path} does not exist after git clone.",
                style="bold red",
            )
            raise typer.Exit(1)
        
        console.print(
            f"  ✅ Base monitor service cloned successfully.", style="green"
        )

        # --- Deploy Monitor Service ---
        success = deploy_monitor_service(
            powerloom_chain_name=selected_powerloom_chain_name_upper,
            wallet_address=final_wallet_address,
            webhook_url=final_webhook_url,
            webhook_service=final_webhook_service,
            slots_to_ignore=slots_to_ignore,
            base_monitor_repo_path=base_monitor_clone_path,
            chain_config=chain_data.chain_config,
            market_config=selected_market_obj,
        )

        if success:
            console.print(
                f"✅ Monitor service deployment completed successfully for {selected_powerloom_chain_name_upper}.",
                style="bold green",
            )
        else:
            console.print(
                f"❌ Monitor service deployment failed for {selected_powerloom_chain_name_upper}.",
                style="bold red",
            )
            raise typer.Exit(1)

    finally:
        # --- Cleanup temporary base clone ---
        if base_monitor_clone_path.exists():
            console.print(
                f"🧹 Cleaning up temporary base monitor clone at {base_monitor_clone_path}...",
                style="dim",
            )
            try:
                shutil.rmtree(base_monitor_clone_path)
                console.print("  ✅ Cleanup successful.", style="dim green")
            except OSError as e:
                console.print(
                    f"  ⚠️ Error cleaning up temporary clone {base_monitor_clone_path}: {e}",
                    style="yellow",
                )
