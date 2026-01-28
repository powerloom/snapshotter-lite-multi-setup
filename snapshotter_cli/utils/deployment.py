import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional

from snapshotter_cli.utils.console import console
from snapshotter_cli.utils.models import (  # PowerloomChainConfig is the one with .name
    ChainConfig,
    MarketConfig,
)

from .system_checks import does_screen_session_exist

SNAPSHOTTER_LITE_V2_DIR = Path("snapshotter-lite-v2")
ENV_EXAMPLE_BASENAME = "env.example"

CONFIG_ENV_FILENAME_TEMPLATE = ".env.{}.{}.{}"

# Directory for storing env files in user's home directory
CONFIG_DIR = Path.home() / ".powerloom-snapshotter-cli" / "envs"

# Profile-aware directories
CLI_CONFIG_DIR = Path.home() / ".powerloom-snapshotter-cli"
PROFILES_DIR = CLI_CONFIG_DIR / "profiles"
DEFAULT_PROFILE = "default"


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


def run_git_command(command: list[str], cwd: Path, desc: str):
    """Helper to run a Git command and handle output/errors."""
    git_executable = shutil.which("git")
    if not git_executable:
        console.print(
            "    ❌ Error: Git command not found. shutil.which('git') returned None. Is Git installed and in your PATH?",
            style="bold red",
        )
        return False

    if command and command[0] == "git":
        full_command = [git_executable] + command[1:]
    else:
        full_command = command

    console.print(
        f"  ↪️ Running Git command: {' '.join(full_command)} in {cwd}", style="dim"
    )
    try:
        env = os.environ.copy()
        process = subprocess.run(
            full_command, cwd=cwd, capture_output=True, text=True, check=True, env=env
        )
        console.print(f"    ✅ {desc} successful.", style="dim green")
        if process.stdout:
            for line in process.stdout.strip().split("\n"):
                console.print(f"      [dim]{line}[/dim]")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"    ❌ Error during {desc}: {e}", style="bold red")
        console.print(f"    Stderr: {e.stderr}", style="red")
        return False
    except FileNotFoundError:
        console.print(
            "    ❌ Error: Git command not found (FileNotFoundError). This is unexpected after shutil.which check.",
            style="bold red",
        )
        return False


def run_os_system_command(command_str: str, instance_dir_name: str, action_desc: str):
    """Helper to run a generic os.system command and provide feedback."""
    console.print(
        f"  ⚙️ Running: {action_desc} for {instance_dir_name} -> `{command_str}`",
        style="dim",
    )
    try:
        exit_code = os.system(command_str)
        if exit_code == 0:
            console.print(
                f"    ✅ {action_desc} for {instance_dir_name} initiated.",
                style="dim green",
            )
            return True
        else:
            console.print(
                f"    ❌ Error during {action_desc} for {instance_dir_name}. Exit code: {exit_code}",
                style="bold red",
            )
            return False
    except Exception as e:
        console.print(
            f"    ❌ Exception during {action_desc} for {instance_dir_name}: {e}",
            style="bold red",
        )
        return False


def deploy_snapshotter_instance(
    powerloom_chain_config: ChainConfig,  # Config for the Powerloom chain (e.g., devnet, mainnet)
    market_config: MarketConfig,  # Config for the specific data market (e.g., UNISWAPV2 on ETH-MAINNET)
    slot_id: int,
    signer_address: str,
    signer_private_key: str,
    source_chain_rpc_url: str,  # RPC URL for the market's source chain (e.g., ETH-MAINNET RPC)
    base_snapshotter_lite_repo_path: Path,  # New parameter for the path to the base clone
    build_sh_args_param: str,  # New parameter for dynamic build.sh arguments
    active_profile: Optional[str] = None,  # Optional profile name to load env from profile directory
) -> bool:
    """
    Deploys a single snapshotter-lite-v2 instance for a given slot and market.
    Manages directory creation, git cloning, .env file generation, and docker compose.
    Returns True on success, False on failure.
    """
    console.print(
        f"⚙️  Starting deployment for Market [bold cyan]{market_config.name}[/bold cyan] on Powerloom Chain [bold magenta]{powerloom_chain_config.name}[/bold magenta], Slot [bold blue]{slot_id}[/bold blue]",
        style="green",
    )

    # 1. Determine Paths
    norm_pl_chain_name = powerloom_chain_config.name.lower()
    pl_chain_name_upper = powerloom_chain_config.name.upper()
    norm_market_name = market_config.name.lower()  # For paths, usually lower
    market_name_upper = (
        market_config.name.upper()
    )  # For display or specific naming like in multi_clone
    norm_source_chain_name_for_path = market_config.sourceChain.lower()
    source_chain_prefix_upper = market_config.sourceChain.split("-")[0].upper()

    instance_subpath = f"{norm_pl_chain_name}/{norm_market_name}_{norm_source_chain_name_for_path}/slot-{slot_id}"
    instance_dir = SNAPSHOTTER_LITE_V2_DIR / instance_subpath
    # e.g., mainnet-UNISWAPV2-ETH (lowercase chain name to match build.sh expectations)
    env_file_suffix = (
        f"{norm_pl_chain_name}-{market_name_upper}-{source_chain_prefix_upper}"
    )
    env_file_path = instance_dir / f".env-{env_file_suffix}"

    console.print(f"  📂 Deployment directory: {instance_dir}")

    if instance_dir.exists():
        console.print(
            f"  ⚠️ Instance directory {instance_dir} already exists. Removing for a fresh deployment.",
            style="yellow",
        )
        try:
            shutil.rmtree(instance_dir)
        except OSError as e:
            console.print(
                f"  ❌ Could not remove existing directory {instance_dir}: {e}",
                style="bold red",
            )
            return False

    try:
        instance_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        console.print(
            f"  ❌ Could not create instance directory {instance_dir}: {e}",
            style="bold red",
        )
        return False

    # 2. Copy from base snapshotter-lite-v2 clone
    console.print(
        f"  📂 Copying base snapshotter-lite-v2 from {base_snapshotter_lite_repo_path} to {instance_dir}",
        style="dim",
    )
    try:
        # instance_dir is already created and empty/cleaned at this point.
        # shutil.copytree copies the *contents* of src into dst.
        # dirs_exist_ok=True allows dst to exist.
        shutil.copytree(
            base_snapshotter_lite_repo_path, instance_dir, dirs_exist_ok=True
        )
        console.print(
            f"    ✅ Base snapshotter copied successfully.", style="dim green"
        )
        # Note: Local collector repository cloning is handled by build.sh, not here
    except Exception as e:
        console.print(
            f"  ❌ Error copying base snapshotter files from {base_snapshotter_lite_repo_path} to {instance_dir}: {e}",
            style="bold red",
        )
        return False

    # --- .env Generation ---
    final_env_vars: Dict[str, str] = {}

    # 1. Load from pre-configured namespaced .env file (if exists)
    # This forms the base. User can put any specific overrides here.
    norm_pl_chain_name_for_file = powerloom_chain_config.name.lower()
    norm_market_name_for_file = market_config.name.lower()
    norm_source_chain_name_for_file = market_config.sourceChain.lower().replace(
        "-", "_"
    )

    potential_config_filename = CONFIG_ENV_FILENAME_TEMPLATE.format(
        norm_pl_chain_name_for_file,
        norm_market_name_for_file,
        norm_source_chain_name_for_file,
    )

    # Check profile directory first (if active_profile is provided)
    # This follows the same pattern used in cli.py for loading profile envs
    config_file_path = None
    if active_profile:
        from snapshotter_cli.utils.profile import get_profile_env_path
        profile_config_path = get_profile_env_path(
            active_profile,
            norm_pl_chain_name_for_file,
            norm_market_name_for_file,
            norm_source_chain_name_for_file,
        )
        if profile_config_path.exists():
            config_file_path = profile_config_path
            console.print(
                f"  ℹ️ Found pre-configured .env template in profile '{active_profile}': {config_file_path}. Loading it.",
                style="dim",
            )
            final_env_vars.update(parse_env_file_vars(str(config_file_path)))
    
    # Fallback to legacy CONFIG_DIR if profile file not found
    if not config_file_path or not config_file_path.exists():
        legacy_config_file_path = CONFIG_DIR / potential_config_filename
        if legacy_config_file_path.exists():
            console.print(
                f"  ℹ️ Found pre-configured .env template in legacy config directory: {legacy_config_file_path}. Loading it.",
                style="dim",
            )
            final_env_vars.update(parse_env_file_vars(str(legacy_config_file_path)))
        else:
            # Check current directory for backward compatibility
            cwd_config_file_path = Path(os.getcwd()) / potential_config_filename
            if cwd_config_file_path.exists():
                console.print(
                    f"  ⚠️ Found legacy env file in current directory: {cwd_config_file_path}. Consider moving it to profile directory.",
                    style="yellow",
                )
                final_env_vars.update(parse_env_file_vars(str(cwd_config_file_path)))
            else:
                console.print(
                    f"  ℹ️ No pre-configured .env template found. Using minimal core settings.",
                    style="dim",
                )

    # 2. Set essential/resolved values (these take highest precedence and will overwrite template if keys conflict)
    final_env_vars["OVERRIDE_DEFAULTS"] = "true"
    final_env_vars["SLOT_ID"] = str(slot_id)
    final_env_vars["SIGNER_ACCOUNT_ADDRESS"] = signer_address
    final_env_vars["SIGNER_ACCOUNT_PRIVATE_KEY"] = signer_private_key
    final_env_vars["POWERLOOM_RPC_URL"] = str(powerloom_chain_config.rpcURL).rstrip("/")
    final_env_vars["SOURCE_RPC_URL"] = source_chain_rpc_url

    # Add BDS-specific environment variables for BDS_DEVNET_ALPHA_UNISWAPV3
    if market_config.name.upper() == "BDS_DEVNET_ALPHA_UNISWAPV3":
        final_env_vars["DEV_MODE"] = "true"
        final_env_vars.setdefault("LOCAL_COLLECTOR_P2P_PORT", "8001")
        # Health check port for local collector (default: 8080, can be overridden in pre-configured env)
        final_env_vars.setdefault("LOCAL_COLLECTOR_HEALTH_CHECK_PORT", "8080")
        # P2P Discovery configuration for DSV devnet
        final_env_vars["RENDEZVOUS_POINT"] = "powerloom-dsv-devnet-alpha"
        final_env_vars["GOSSIPSUB_SNAPSHOT_SUBMISSION_PREFIX"] = "/powerloom/dsv-devnet-alpha/snapshot-submissions"
        
        # Extract bootstrap nodes from market config (from curated datamarkets JSON)
        if market_config.bootstrapNodes and len(market_config.bootstrapNodes) > 0:
            final_env_vars["BOOTSTRAP_NODE_ADDRS"] = ",".join(market_config.bootstrapNodes)
        else:
            # This should not happen for BDS_DEVNET_ALPHA_UNISWAPV3 as bootstrap nodes should be in JSON
            console.print(
                f"  ⚠️ No bootstrap nodes found in market config for {market_config.name}. BOOTSTRAP_NODE_ADDRS will not be set.",
                style="yellow",
            )
            # Don't set BOOTSTRAP_NODE_ADDRS if not found - let it be undefined/empty
        
        # Connection manager configuration (required for dsv-p2p branch local collector)
        # Using permissive values (100/400) for publisher role to prevent aggressive pruning
        final_env_vars["CONN_MANAGER_LOW_WATER"] = "100"
        final_env_vars["CONN_MANAGER_HIGH_WATER"] = "400"
        
        # Stream Pool Configuration (for centralized sequencer)
        final_env_vars["MAX_STREAM_POOL_SIZE"] = "2"
        final_env_vars["MAX_STREAM_QUEUE_SIZE"] = "1000"
        final_env_vars["STREAM_HEALTH_CHECK_TIMEOUT_MS"] = "5000"
        final_env_vars["STREAM_WRITE_TIMEOUT_MS"] = "5000"
        final_env_vars["MAX_WRITE_RETRIES"] = "3"
        final_env_vars["MAX_CONCURRENT_WRITES"] = "10"
        final_env_vars["STREAM_POOL_HEALTH_CHECK_INTERVAL"] = "60000"  # milliseconds
        final_env_vars["CONNECTION_REFRESH_INTERVAL_SEC"] = "300"
        final_env_vars["WRITE_SEMAPHORE_TIMEOUT_SEC"] = "5"
        
        # Centralized Sequencer Control
        # Set to "false" to disable all submissions to centralized sequencer (mesh-only mode)
        # Set to "true" to enable dual submission (both centralized sequencer and mesh)
        final_env_vars["CENTRALIZED_SEQUENCER_ENABLED"] = "false"
        
        # Mesh Submission Concurrency Controls
        # Rate limiting for mesh submissions to prevent overwhelming the gossipsub network
        final_env_vars["MESH_SUBMISSION_RATE_LIMIT"] = "100"
        final_env_vars["MESH_SUBMISSION_BURST_SIZE"] = "200"
        # Maximum concurrent mesh publish operations (goroutine limit)
        final_env_vars["MAX_MESH_PUBLISH_GOROUTINES"] = "500"
        # Maximum queued mesh submissions when rate limited
        final_env_vars["MESH_PUBLISH_QUEUE_SIZE"] = "1000"
        
        # Other Configuration
        final_env_vars["DATA_MARKET_IN_REQUEST"] = "true"
        
        # PUBLIC_IP left blank for publisher role (lite nodes can run from low-powered instances)
        final_env_vars["PUBLIC_IP"] = ""
    elif market_config.name.upper() == "BDS_MAINNET_ALPHA_UNISWAPV3":
        final_env_vars["DEV_MODE"] = "true"
        final_env_vars.setdefault("LOCAL_COLLECTOR_P2P_PORT", "8001")
        # Health check port for local collector (default: 8080, can be overridden in pre-configured env)
        final_env_vars.setdefault("LOCAL_COLLECTOR_HEALTH_CHECK_PORT", "8080")
        # P2P Discovery configuration for DSV mainnet
        final_env_vars["RENDEZVOUS_POINT"] = "powerloom-dsv-mainnet-alpha"
        final_env_vars["GOSSIPSUB_SNAPSHOT_SUBMISSION_PREFIX"] = "/powerloom/dsv-mainnet-alpha/snapshot-submissions"
        
        # Extract bootstrap nodes from market config (from curated datamarkets JSON)
        if market_config.bootstrapNodes and len(market_config.bootstrapNodes) > 0:
            final_env_vars["BOOTSTRAP_NODE_ADDRS"] = ",".join(market_config.bootstrapNodes)
        else:
            # This should not happen for BDS_MAINNET_ALPHA_UNISWAPV3 as bootstrap nodes should be in JSON
            console.print(
                f"  ⚠️ No bootstrap nodes found in market config for {market_config.name}. BOOTSTRAP_NODE_ADDRS will not be set.",
                style="yellow",
            )
            # Don't set BOOTSTRAP_NODE_ADDRS if not found - let it be undefined/empty
        
        # Connection manager configuration (required for dsv-p2p branch local collector)
        # Using permissive values (100/400) for publisher role to prevent aggressive pruning
        final_env_vars["CONN_MANAGER_LOW_WATER"] = "100"
        final_env_vars["CONN_MANAGER_HIGH_WATER"] = "400"
        
        # Stream Pool Configuration (for centralized sequencer)
        final_env_vars["MAX_STREAM_POOL_SIZE"] = "2"
        final_env_vars["MAX_STREAM_QUEUE_SIZE"] = "1000"
        final_env_vars["STREAM_HEALTH_CHECK_TIMEOUT_MS"] = "5000"
        final_env_vars["STREAM_WRITE_TIMEOUT_MS"] = "5000"
        final_env_vars["MAX_WRITE_RETRIES"] = "3"
        final_env_vars["MAX_CONCURRENT_WRITES"] = "10"
        final_env_vars["STREAM_POOL_HEALTH_CHECK_INTERVAL"] = "60000"  # milliseconds
        final_env_vars["CONNECTION_REFRESH_INTERVAL_SEC"] = "300"
        final_env_vars["WRITE_SEMAPHORE_TIMEOUT_SEC"] = "5"
        
        # Centralized Sequencer Control
        # Set to "false" to disable all submissions to centralized sequencer (mesh-only mode)
        # Set to "true" to enable dual submission (both centralized sequencer and mesh)
        final_env_vars["CENTRALIZED_SEQUENCER_ENABLED"] = "false"
        
        # Mesh Submission Concurrency Controls
        # Rate limiting for mesh submissions to prevent overwhelming the gossipsub network
        final_env_vars["MESH_SUBMISSION_RATE_LIMIT"] = "100"
        final_env_vars["MESH_SUBMISSION_BURST_SIZE"] = "200"
        # Maximum concurrent mesh publish operations (goroutine limit)
        final_env_vars["MAX_MESH_PUBLISH_GOROUTINES"] = "500"
        # Maximum queued mesh submissions when rate limited
        final_env_vars["MESH_PUBLISH_QUEUE_SIZE"] = "1000"
        
        # Other Configuration
        final_env_vars["DATA_MARKET_IN_REQUEST"] = "true"
        
        # PUBLIC_IP left blank for publisher role (lite nodes can run from low-powered instances)
        final_env_vars["PUBLIC_IP"] = ""

    final_env_vars["DATA_MARKET_CONTRACT"] = market_config.contractAddress
    final_env_vars["PROTOCOL_STATE_CONTRACT"] = (
        market_config.powerloomProtocolStateContractAddress
    )
    final_env_vars["SNAPSHOT_CONFIG_REPO"] = str(market_config.config.repo)
    final_env_vars["SNAPSHOT_CONFIG_REPO_BRANCH"] = market_config.config.branch

    final_env_vars["SNAPSHOTTER_COMPUTE_REPO"] = str(market_config.compute.repo)
    final_env_vars["SNAPSHOTTER_COMPUTE_REPO_BRANCH"] = market_config.compute.branch

    final_env_vars["POWERLOOM_CHAIN"] = norm_pl_chain_name
    final_env_vars["NAMESPACE"] = market_name_upper
    final_env_vars["SOURCE_CHAIN"] = source_chain_prefix_upper
    final_env_vars["FULL_NAMESPACE"] = env_file_suffix
    final_env_vars["DOCKER_NETWORK_NAME"] = f"snapshotter-lite-v2-{env_file_suffix}"

    # Add missing vars from multi_clone.py, using defaults or loading from pre-config/env
    # For simplicity, pre-loaded 'final_env_vars' from a namespaced .env file can override these defaults.
    final_env_vars.setdefault("LOCAL_COLLECTOR_PORT", "50051")
    final_env_vars.setdefault(
        "MAX_STREAM_POOL_SIZE", "2"
    )  # Default from multi_clone, may need adjustment based on CPU as in multi_clone
    # STREAM_POOL_HEALTH_CHECK_INTERVAL is in milliseconds (default: 60000 = 60 seconds)
    # Only set default if not already set (BDS deployments will override with correct value)
    if "STREAM_POOL_HEALTH_CHECK_INTERVAL" not in final_env_vars:
        final_env_vars["STREAM_POOL_HEALTH_CHECK_INTERVAL"] = "60000"
    final_env_vars.setdefault("DATA_MARKET_IN_REQUEST", "false")
    final_env_vars.setdefault(
        "LOCAL_COLLECTOR_IMAGE_TAG", "latest"
    )  # Simplified default
    final_env_vars.setdefault("CONNECTION_REFRESH_INTERVAL_SEC", "60")
    final_env_vars.setdefault("TELEGRAM_NOTIFICATION_COOLDOWN", "300")

    # TELEGRAM_REPORTING_URL and TELEGRAM_CHAT_ID will be included if they were in the pre-configured .env
    # or global env vars that got loaded into namespaced_env_content (passed to get_credential originally).
    # If not, they remain absent, which is fine if they are optional.
    # To explicitly set them to empty if not found in template, it would be:
    # final_env_vars.setdefault("TELEGRAM_REPORTING_URL", "")
    # final_env_vars.setdefault("TELEGRAM_CHAT_ID", "")

    try:
        with open(env_file_path, "w") as f:
            f.write(
                f"# Auto-generated .env for {market_config.name} on {powerloom_chain_config.name}, Slot {slot_id}\n"
            )
            f.write(f"# Deployment Path: {instance_dir}\n\n")
            for key, value in final_env_vars.items():
                f.write(f"{key}={value}\n")
        console.print(f"  📄 Generated .env file: {env_file_path}", style="dim green")
    except IOError as e:
        console.print(
            f"  ❌ Error writing .env file {env_file_path}: {e}", style="bold red"
        )
        return False

    # --- Spawning instance using screen and build.sh (from multi_clone.py) ---
    console.print(
        f"  🚀 Spawning instance for slot {slot_id} market {market_config.name} via screen and build.sh...",
        style="dim blue",
    )

    # Let's use a screen name based on the instance_dir structure to ensure uniqueness and clarity.
    screen_session_name = f"pl_{norm_pl_chain_name}_{norm_market_name}_{slot_id}"

    # Change current working directory to instance_dir before running os.system commands for screen
    original_cwd = Path(os.getcwd())
    try:
        os.chdir(instance_dir)

        # Check if screen session already exists
        if does_screen_session_exist(screen_session_name):
            console.print(
                f"  ❌ Error: Screen session named '{screen_session_name}' already exists.",
                style="bold red",
            )
            console.print(
                f"     Please clean it up manually (e.g., using 'screen -X -S {screen_session_name} quit' or 'screen -wipe') and try again.",
                style="yellow",
            )
            os.chdir(original_cwd)  # Restore CWD
            return False

        screen_create_cmd = f"screen -dmS {screen_session_name}"
        if not run_os_system_command(
            screen_create_cmd, screen_session_name, "Create screen session"
        ):
            os.chdir(original_cwd)  # Restore CWD
            return False

        build_command_to_stuff = f"./build.sh {build_sh_args_param}\n"
        screen_stuff_cmd = (
            f'screen -r {screen_session_name} -p 0 -X stuff "{build_command_to_stuff}"'
        )

        if not run_os_system_command(
            screen_stuff_cmd, screen_session_name, "Send build.sh command"
        ):
            os.chdir(original_cwd)  # Restore CWD
            run_os_system_command(
                f"screen -X -S {screen_session_name} quit",
                screen_session_name,
                "Quit screen session on error",
            )
            return False

        console.print(
            f"    ✅ Instance for slot {slot_id} (market: {market_config.name}) launched in screen session: {screen_session_name}",
            style="green",
        )

        # Sleep to allow instance to start, similar to multi_clone.py
        # The duration might need adjustment. multi_clone.py uses 30s for first, 10s for others.
        sleep_duration = 10  # Using a fixed sleep for now.
        console.print(
            f"    ⏳ Sleeping for {sleep_duration} seconds to allow instance to initialize...",
            style="dim",
        )
        time.sleep(sleep_duration)

    except Exception as e:
        console.print(
            f"  ❌ Exception during screen/build.sh execution: {e}", style="bold red"
        )
        os.chdir(original_cwd)  # Restore CWD
        return False
    finally:
        os.chdir(original_cwd)  # Always restore CWD

    # Removing direct docker compose calls
    # try:
    #     process = subprocess.run(["docker", "compose", "up", "-d", "--build"], cwd=instance_dir, capture_output=True, text=True, check=True)
    # ... (rest of docker compose logic removed)

    console.print(
        f"✅ Deployment attempt for Market [bold cyan]{market_config.name}[/bold cyan], Slot [bold blue]{slot_id}[/bold blue] initiated via screen.",
        style="bold green",
    )
    return True


def calculate_connection_refresh_interval(num_slots: int) -> int:
    """Calculate the connection refresh interval based on number of slots.

    Args:
        num_slots: Number of slots being deployed

    Returns:
        Recommended refresh interval in seconds
    """
    # Base minimum interval
    MIN_INTERVAL = 60  # seconds

    if num_slots <= 10:
        return MIN_INTERVAL

    # Linear scaling with some adjustments
    # Formula: 4 seconds per slot + baseline of 60
    interval = (4 * num_slots) + MIN_INTERVAL

    # Cap at reasonable maximum
    MAX_INTERVAL = 900  # 15 minutes
    return min(interval, MAX_INTERVAL)
