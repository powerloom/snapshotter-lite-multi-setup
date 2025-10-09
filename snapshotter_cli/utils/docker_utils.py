import subprocess
from typing import Dict, List, Optional

from snapshotter_cli.utils.console import console


def get_docker_container_status_for_instance(
    slot_id: Optional[str],
    chain_name_upper: Optional[str],
    market_name_upper: Optional[str],
) -> List[Dict[str, str]]:
    """
    Gets Docker container status for containers matching patterns derived from slot, chain, and market.

    Patterns are based on observed names:
    - Snapshotter node: snapshotter-lite-v2-{SLOT_ID}-{CHAIN_UPPER}-{MARKET_UPPER}-{SOURCE_PREFIX_UPPER}
    - Local collector: snapshotter-lite-local-collector-{CHAIN_UPPER}-{MARKET_UPPER}-{SOURCE_PREFIX_UPPER}
    Since SOURCE_PREFIX_UPPER is not available from screen name, we match the other parts.
    """
    containers = []
    # Ensure essential parts are available for meaningful filtering
    if not chain_name_upper or not market_name_upper:
        # slot_id might be missing if parsing failed, but chain/market are more critical for collector
        console.print(
            "[dim]Skipping Docker search: chain name or data market name not provided for filtering.[/dim]",
            style="yellow",
        )
        return containers

    try:
        command = [
            "docker",
            "ps",
            "-a",
            "--format",
            "{{.Names}}\\t{{.Status}}\\t{{.ID}}",
        ]

        process = subprocess.run(
            command, capture_output=True, text=True, check=True, timeout=10
        )

        output_lines = process.stdout.strip().splitlines()
        for line in output_lines:
            if not line.strip():
                continue

            # Split by any whitespace, as tabs may be converted to spaces in output
            raw_parts = line.split()

            if (
                len(raw_parts) >= 2
            ):  # Minimum: name and ID. Status can be empty or multi-word.
                name = raw_parts[0]
                container_id = raw_parts[-1]

                if len(raw_parts) > 2:
                    status = " ".join(raw_parts[1:-1])
                else:  # Only name and ID, so status is considered empty
                    status = ""
            else:
                # Log this unexpected line format and skip it
                console.print(
                    f"[dim yellow]⚠️ Skipping Docker ps output line: not enough parts after space split: '{line}'[/dim yellow]"
                )
                continue

            name_upper = (
                name.upper()
            )  # For case-insensitive comparison of constant parts

            # Check for main snapshotter node pattern
            # e.g., snapshotter-lite-v2-5483-MAINNET-UNISWAPV2-ETH
            is_node_match = False
            if slot_id:  # Slot ID is crucial for the node container
                # Check if name contains "snapshotter-lite-v2", slot_id, chain_name_upper, and market_name_upper
                # Order might not be fixed if project name convention changes, so check for presence
                if (
                    f"SNAPSHOTTER-LITE-V2" in name_upper
                    and slot_id
                    in name  # slot_id is numeric, check in original case name
                    and chain_name_upper in name_upper
                    and market_name_upper in name_upper
                ):
                    is_node_match = True

            # Check for local collector pattern
            # e.g., snapshotter-lite-local-collector-MAINNET-UNISWAPV2-ETH
            is_collector_match = False
            # Collector name does not seem to include slot_id based on user's example
            if (
                f"SNAPSHOTTER-LITE-LOCAL-COLLECTOR" in name_upper
                and chain_name_upper in name_upper
                and market_name_upper in name_upper
            ):
                is_collector_match = True

            if is_node_match or is_collector_match:
                containers.append(
                    {
                        "name": name.strip(),
                        "status": status.strip(),
                        "id": container_id.strip(),
                    }
                )

        if not containers:
            console.print(
                f"[dim]No Docker containers found matching patterns for slot {slot_id}, chain {chain_name_upper}, market {market_name_upper}[/dim]",
                style="yellow",
            )

        return containers

    except FileNotFoundError:
        console.print(
            "❌ 'docker' command not found. Is Docker installed and running?",
            style="red",
        )
        return []  # Return empty list
    except subprocess.CalledProcessError as e:
        console.print(
            f"[dim]Error running 'docker ps': {e.stderr.strip() if e.stderr else 'No stderr'}[/dim]",
            style="yellow",
        )
        return []
    except subprocess.TimeoutExpired:
        console.print("⏰ Timeout while running 'docker ps'.", style="yellow")
        return []
    except Exception as e:
        console.print(
            f"⚠️ Unexpected error while getting Docker container status: {e}",
            style="yellow",
        )
        return []
