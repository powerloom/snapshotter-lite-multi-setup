import os
import subprocess
from typing import Dict, List, Tuple

import typer
from rich.panel import Panel

from snapshotter_cli.utils.console import console


def check_sudo_access() -> bool:
    """Check if we have sudo access."""
    try:
        subprocess.run(["sudo", "-n", "true"], capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def run_with_sudo(command: List[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command with sudo if necessary."""
    try:
        # Try without sudo first
        return subprocess.run(command, **kwargs, check=True)
    except (subprocess.CalledProcessError, PermissionError):
        # If failed, try with sudo
        if not check_sudo_access():
            console.print("⚠️  Docker commands require sudo access", style="yellow")
            if not typer.confirm("Would you like to proceed with sudo?"):
                raise typer.Abort()
        return subprocess.run(["sudo"] + command, **kwargs, check=True)


def check_command_exists(command: str) -> bool:
    """Check if a command exists in the system."""
    try:
        subprocess.run(["which", command], capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def check_docker_status() -> Tuple[bool, str]:
    """Check if Docker is installed and running."""
    if not check_command_exists("docker"):
        return False, "Docker is not installed"

    try:
        run_with_sudo(["docker", "info"], capture_output=True)
        return True, "Docker is installed and running"
    except subprocess.CalledProcessError:
        return False, "Docker daemon is not running"


def check_docker_compose() -> Tuple[bool, str]:
    """Check if docker-compose is available."""
    if check_command_exists("docker-compose"):
        return True, "docker-compose is available"

    try:
        run_with_sudo(["docker", "compose", "version"], capture_output=True)
        return True, "Docker Compose plugin is available"
    except subprocess.CalledProcessError:
        return False, "Neither docker-compose nor Docker Compose plugin found"


def get_powerloom_containers(
    slot_id: str = None, chain: str = None, market: str = None
) -> List[Dict[str, str]]:
    """Get list of Powerloom containers with their IDs and names.

    Args:
        slot_id: Optional slot ID to filter by
        chain: Optional chain name to filter by (e.g., 'mainnet', 'devnet')
        market: Optional data market name to filter by (e.g., 'uniswapv2', 'aavev3')
    """
    try:
        # Create a list of filters for different container name patterns
        filters = [
            "name=snapshotter-lite-v2",
            "name=powerloom-premainnet-",
            "name=powerloom-testnet-",
            "name=powerloom-mainnet-",
            "name=local-collector",
        ]
        # Run docker ps with multiple filters and format to get just ID and name
        result = run_with_sudo(
            ["docker", "ps", "-a", "--format", "{{.ID}}\t{{.Names}}"]
            + sum([["--filter", f] for f in filters], []),
            capture_output=True,
            text=True,
        )
        containers = []
        for line in result.stdout.strip().split("\n"):
            if line:
                container_id, container_name = line.strip().split("\t")

                # Apply filters if provided
                name_upper = container_name.upper()

                # Filter by slot_id (numeric, check in original case)
                if slot_id and slot_id not in container_name:
                    continue

                # Filter by chain (case-insensitive)
                if chain and chain.upper() not in name_upper:
                    continue

                # Filter by market (case-insensitive)
                if market and market.upper() not in name_upper:
                    continue

                containers.append(
                    {"id": container_id.strip(), "name": container_name.strip()}
                )
        return containers
    except subprocess.CalledProcessError:
        return []


def get_powerloom_networks() -> List[str]:
    """Get list of Powerloom networks."""
    try:
        result = run_with_sudo(
            [
                "docker",
                "network",
                "ls",
                "--filter",
                "name=snapshotter-lite-v2",
                "--format",
                "{{.Name}}",
            ],
            capture_output=True,
            text=True,
        )
        return [line for line in result.stdout.split("\n") if line]
    except subprocess.CalledProcessError:
        return []


def get_network_containers(network_name: str) -> List[str]:
    """Get Powerloom containers attached to a specific Docker network.

    Args:
        network_name: Name of the Docker network to inspect

    Returns:
        List of Powerloom container names attached to the network
    """
    try:
        # Inspect the network and get all attached container names
        result = run_with_sudo(
            [
                "docker",
                "network",
                "inspect",
                network_name,
                "--format",
                "{{range .Containers}}{{.Name}} {{end}}",
            ],
            capture_output=True,
            text=True,
        )

        # Parse container names from output
        all_containers = result.stdout.strip().split()

        # Filter to only include Powerloom-related containers
        # This ensures we only count relevant containers when deciding to remove networks
        powerloom_patterns = [
            "snapshotter-lite-v2",
            "powerloom-premainnet-",
            "powerloom-testnet-",
            "powerloom-mainnet-",
            "local-collector",
        ]

        powerloom_containers = [
            container
            for container in all_containers
            if any(pattern in container for pattern in powerloom_patterns)
        ]

        return powerloom_containers
    except subprocess.CalledProcessError:
        # If network doesn't exist or inspection fails, return empty list
        return []


def get_powerloom_screen_sessions(
    slot_id: str = None, chain: str = None, market: str = None
) -> List[Dict[str, str]]:
    """Get list of Powerloom screen sessions.

    Args:
        slot_id: Optional slot ID to filter by
        chain: Optional chain name to filter by (e.g., 'mainnet', 'devnet')
        market: Optional data market name to filter by (e.g., 'uniswapv2', 'aavev3')
    """
    try:
        # Use screen -ls to list sessions and grep for powerloom patterns
        result = subprocess.run(["screen", "-ls"], capture_output=True, text=True)
        if result.returncode > 1:  # screen -ls returns 1 if no sessions exist
            return []

        # Parse screen output and look for powerloom sessions
        sessions = []
        for line in result.stdout.split("\n"):
            if any(
                pattern in line
                for pattern in [
                    "powerloom-premainnet",
                    "powerloom-testnet",
                    "powerloom-mainnet",
                    "snapshotter",
                    "pl_",
                ]
            ):
                # Extract session ID from the line (first number in the line)
                session_id = line.split(".")[0].strip()
                if session_id.isdigit():
                    # Apply filters if provided
                    line_upper = line.upper()

                    # Filter by slot_id (numeric, check in original case)
                    if slot_id and slot_id not in line:
                        continue

                    # Filter by chain (case-insensitive)
                    if chain and chain.upper() not in line_upper:
                        continue

                    # Filter by market (case-insensitive)
                    if market and market.upper() not in line_upper:
                        continue

                    sessions.append({"id": session_id, "name": line.strip()})
        return sessions
    except subprocess.CalledProcessError:
        return []


def cleanup_resources(
    force: bool = False,
    slot_id: str = None,
    chain: str = None,
    market: str = None,
) -> None:
    """Clean up Docker resources.

    Args:
        force: Skip confirmation prompts
        slot_id: Optional slot ID to filter by
        chain: Optional chain name to filter by
        market: Optional data market name to filter by
    """
    # Get resources to clean based on filters
    containers = get_powerloom_containers(slot_id=slot_id, chain=chain, market=market)
    screen_sessions = get_powerloom_screen_sessions(
        slot_id=slot_id, chain=chain, market=market
    )

    if screen_sessions and (
        force
        or typer.confirm(
            "Would you like to terminate existing Powerloom screen sessions?"
        )
    ):
        console.print("Terminating screen sessions...", style="yellow")
        for session in screen_sessions:
            try:
                subprocess.run(["kill", session["id"]], check=True)
                console.print(
                    f"✅ Terminated screen session: {session['name']}", style="green"
                )
            except subprocess.CalledProcessError as e:
                console.print(
                    f"⚠️  Failed to terminate screen session {session['name']}: {e}",
                    style="red",
                )
                continue
        console.print("Screen session cleanup completed", style="green")

    if containers and (
        force
        or typer.confirm(
            "Would you like to stop and remove existing Powerloom containers?"
        )
    ):
        console.print("Stopping and removing containers...", style="yellow")
        for container in containers:
            try:
                container_id = container["id"]
                container_name = container["name"]
                run_with_sudo(["docker", "stop", container_id], capture_output=True)
                run_with_sudo(["docker", "rm", container_id], capture_output=True)
                console.print(
                    f"✅ Removed container: {container_name} ({container_id})",
                    style="green",
                )
            except subprocess.CalledProcessError as e:
                console.print(
                    f"⚠️  Failed to remove container {container_name} ({container_id}): {e}",
                    style="red",
                )
                continue
        console.print("Container cleanup completed", style="green")

    # Smart network cleanup: Only remove networks that have no Powerloom containers attached
    # This handles all scenarios:
    # - Full cleanup (no filters): All containers removed → All networks empty → Remove all
    # - Partial cleanup (e.g., --chain mainnet --market uniswapv2): All containers for that
    #   combo removed → That network empty → Remove only that network
    # - Single slot cleanup (e.g., --slot-id 5481): One container removed → Network still
    #   has other containers → Keep network
    all_networks = get_powerloom_networks()

    if all_networks:
        # Check which networks are empty (no Powerloom containers attached)
        empty_networks = []
        for network in all_networks:
            attached_containers = get_network_containers(network)
            if len(attached_containers) == 0:
                empty_networks.append(network)

        # Only prompt to remove networks that are actually empty
        if empty_networks and (
            force
            or typer.confirm(
                f"Would you like to remove {len(empty_networks)} empty Powerloom network(s)?"
            )
        ):
            console.print("Removing empty networks...", style="yellow")
            for network in empty_networks:
                try:
                    run_with_sudo(
                        ["docker", "network", "rm", network], capture_output=True
                    )
                    console.print(f"✅ Removed network: {network}", style="green")
                except subprocess.CalledProcessError as e:
                    console.print(
                        f"⚠️  Failed to remove network {network}: {e}", style="red"
                    )
                    continue
            console.print("Network cleanup completed", style="green")
        elif empty_networks:
            console.print(
                f"ℹ️  {len(empty_networks)} empty network(s) found but not removed",
                style="blue",
            )
        else:
            console.print(
                "ℹ️  No empty networks found (all networks have active containers)",
                style="blue",
            )


def run_diagnostics(
    clean: bool = False,
    force: bool = False,
    slot_id: str = None,
    chain: str = None,
    market: str = None,
) -> None:
    """Run system diagnostics and optionally clean up resources.

    Args:
        clean: Enable cleanup mode
        force: Skip confirmation prompts
        slot_id: Optional slot ID to filter by
        chain: Optional chain name to filter by
        market: Optional data market name to filter by
    """
    # Check Docker installation and status
    docker_ok, docker_msg = check_docker_status()
    console.print(
        Panel(f"Docker Status: {docker_msg}", style="green" if docker_ok else "red")
    )
    if not docker_ok:
        return

    # Check Docker Compose
    compose_ok, compose_msg = check_docker_compose()
    console.print(
        Panel(
            f"Docker Compose Status: {compose_msg}",
            style="green" if compose_ok else "red",
        )
    )
    if not compose_ok:
        return

    # Show existing resources (apply filters if provided)
    if containers := get_powerloom_containers(
        slot_id=slot_id, chain=chain, market=market
    ):
        console.print("\nExisting Powerloom containers:", style="yellow")
        # Get full container details for display
        try:
            result = run_with_sudo(
                [
                    "docker",
                    "ps",
                    "-a",
                    "--format",
                    "table {{.ID}}\t{{.Image}}\t{{.Command}}\t{{.CreatedAt}}\t{{.Status}}\t{{.Ports}}\t{{.Names}}",
                ]
                + sum(
                    [
                        ["--filter", f]
                        for f in [
                            "name=snapshotter-lite-v2",
                            "name=powerloom-premainnet-",
                            "name=powerloom-testnet-",
                            "name=powerloom-mainnet-",
                            "name=local-collector",
                        ]
                    ],
                    [],
                ),
                capture_output=True,
                text=True,
            )
            for line in result.stdout.split("\n"):
                if line.strip():
                    console.print(f"  • {line}")
        except subprocess.CalledProcessError:
            # Fallback to simple display if detailed view fails
            for container in containers:
                console.print(f"  • {container['name']} ({container['id']})")

    if networks := get_powerloom_networks():
        console.print("\nExisting Powerloom networks:", style="yellow")
        for network in networks:
            console.print(f"  • {network}")

    if screen_sessions := get_powerloom_screen_sessions(
        slot_id=slot_id, chain=chain, market=market
    ):
        console.print("\nExisting Powerloom screen sessions:", style="yellow")
        for session in screen_sessions:
            console.print(f"  • {session['name']}")

    # Clean up if requested
    if clean or (containers or networks or screen_sessions):
        cleanup_resources(force, slot_id=slot_id, chain=chain, market=market)


def diagnose_command(
    clean: bool = False,
    force: bool = False,
    slot_id: str = None,
    chain: str = None,
    market: str = None,
):
    """CLI command handler for diagnose.

    Args:
        clean: Enable cleanup mode
        force: Skip confirmation prompts
        slot_id: Optional slot ID to filter by
        chain: Optional chain name to filter by (e.g., 'mainnet', 'devnet')
        market: Optional data market name to filter by (e.g., 'uniswapv2', 'aavev3')
    """
    # Display filter information if any filters are applied
    filters_applied = []
    if slot_id:
        filters_applied.append(f"Slot ID: {slot_id}")
    if chain:
        filters_applied.append(f"Chain: {chain}")
    if market:
        filters_applied.append(f"Market: {market}")

    if filters_applied:
        console.print(
            f"🔍 Running Powerloom Snapshotter Node Diagnostics (Filters: {', '.join(filters_applied)})...",
            style="bold blue",
        )
    else:
        console.print(
            "🔍 Running Powerloom Snapshotter Node Diagnostics...", style="bold blue"
        )

    run_diagnostics(clean, force, slot_id=slot_id, chain=chain, market=market)
