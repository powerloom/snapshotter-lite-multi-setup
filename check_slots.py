#!/usr/bin/env python3
"""
Script to check which slots are running and which are not.
Compares slots owned by wallet with running Docker containers.
"""

import json
import os
import re
import subprocess
import sys

from dotenv import load_dotenv
from web3 import Web3

POWERLOOM_CHAIN = "mainnet"
SOURCE_CHAIN = "ETH"
POWERLOOM_RPC_URL = "https://rpc-v2.powerloom.network"
PROTOCOL_STATE_CONTRACT = "0x000AA7d3a6a2556496f363B59e56D9aA1881548F"

DATA_MARKET_CHOICE_NAMESPACES = {"1": "AAVEV3", "2": "UNISWAPV2"}


def get_user_slots(contract_obj, wallet_owner_addr):
    """Get all slots owned by the wallet address."""
    holder_slots = contract_obj.functions.getUserOwnedNodeIds(wallet_owner_addr).call()
    return holder_slots


def get_running_slots(namespace=None):
    """
    Get all running slots from Docker containers.

    Args:
        namespace: Optional namespace filter (e.g., "UNISWAPV2")

    Returns:
        dict: Dictionary mapping slot_id to list of container info
    """
    # Build the grep pattern
    if namespace:
        full_namespace = f"{POWERLOOM_CHAIN}-{namespace}-{SOURCE_CHAIN}"
        pattern = f"snapshotter-lite-v2-[0-9]+-{full_namespace}"
    else:
        pattern = f"snapshotter-lite-v2-[0-9]+-{POWERLOOM_CHAIN}"

    # Get running containers
    result = subprocess.run(
        f"docker ps --format '{{{{.Names}}}}' | grep -E '{pattern}'",
        shell=True,
        capture_output=True,
        text=True,
    )

    running_slots = {}
    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            # Extract slot ID from container name
            # Format: snapshotter-lite-v2-{slot_id}-{full_namespace}
            match = re.search(r"snapshotter-lite-v2-(\d+)-", line)
            if match:
                slot_id = int(match.group(1))
                if slot_id not in running_slots:
                    running_slots[slot_id] = []
                running_slots[slot_id].append(line)

    return running_slots


def get_screen_sessions():
    """Get all running screen sessions for Powerloom nodes."""
    result = subprocess.run(
        "screen -ls | grep powerloom",
        shell=True,
        capture_output=True,
        text=True,
    )

    screen_slots = set()
    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            # Extract slot ID from screen name
            # Format: {pid}.powerloom-mainnet-v2-{slot_id}-{namespace}
            match = re.search(r"powerloom-[^-]+-[^-]+-(\d+)-", line)
            if match:
                screen_slots.add(int(match.group(1)))

    return screen_slots


def main():
    # Check if .env file exists
    if not os.path.exists(".env"):
        print("❌ .env file not found, please run bootstrap.sh to create one!")
        sys.exit(1)

    load_dotenv(override=True)

    # Get configuration
    wallet_holder_address = os.getenv("WALLET_HOLDER_ADDRESS")
    powerloom_rpc_url = os.getenv("POWERLOOM_RPC_URL", POWERLOOM_RPC_URL)

    if not wallet_holder_address:
        print("❌ Missing WALLET_HOLDER_ADDRESS environment variable")
        sys.exit(1)

    print("🔍 Checking slot status...\n")

    # Initialize Web3 and contract connections
    try:
        w3 = Web3(Web3.HTTPProvider(powerloom_rpc_url))

        # Load contract ABIs
        with open("snapshotter_cli/utils/abi/ProtocolState.json", "r") as f:
            protocol_state_abi = json.load(f)
        with open("snapshotter_cli/utils/abi/PowerloomNodes.json", "r") as f:
            powerloom_nodes_abi = json.load(f)

        # Test connection
        block_number = w3.eth.get_block_number()
        print(f"✅ Connected to Powerloom RPC (block: {block_number})")
    except Exception as e:
        print(f"❌ Failed to connect to Powerloom RPC: {e}")
        sys.exit(1)

    # Get protocol state contract
    protocol_state_address = w3.to_checksum_address(PROTOCOL_STATE_CONTRACT)
    protocol_state_contract = w3.eth.contract(
        address=protocol_state_address,
        abi=protocol_state_abi,
    )

    slot_contract_address = protocol_state_contract.functions.snapshotterState().call()
    slot_contract_address = w3.to_checksum_address(slot_contract_address)

    # Setup contract instances
    wallet_holder_address = Web3.to_checksum_address(wallet_holder_address)
    slot_contract = w3.eth.contract(
        address=Web3.to_checksum_address(slot_contract_address),
        abi=powerloom_nodes_abi,
    )

    # Get all slots owned by wallet
    print(f"📋 Fetching slots for wallet: {wallet_holder_address}")
    slot_ids = get_user_slots(slot_contract, wallet_holder_address)

    if not slot_ids:
        print("❌ No slots found for wallet holder address")
        return

    print(f"✅ Found {len(slot_ids)} total slots\n")

    # Get running slots from Docker
    print("🐳 Checking running Docker containers...")
    running_slots = get_running_slots()

    # Get screen sessions
    print("📺 Checking screen sessions...")
    screen_slots = get_screen_sessions()

    # Analyze status
    running_slot_ids = set(running_slots.keys())
    owned_slot_ids = set(slot_ids)
    not_running = owned_slot_ids - running_slot_ids
    unknown_running = running_slot_ids - owned_slot_ids

    # Check for slots with containers but no screen sessions
    containers_without_screens = running_slot_ids - screen_slots
    screens_without_containers = screen_slots - running_slot_ids

    print("\n" + "="*80)
    print("📊 SLOT STATUS SUMMARY")
    print("="*80 + "\n")

    # Running slots
    if running_slot_ids:
        print(f"✅ Running slots: {len(running_slot_ids)}")
        sorted_running = sorted(list(running_slot_ids))
        for i in range(0, len(sorted_running), 10):
            batch = sorted_running[i:i+10]
            print(f"   {', '.join(str(slot) for slot in batch)}")
        print()

    # Not running slots
    if not_running:
        print(f"❌ Not running slots: {len(not_running)}")
        sorted_not_running = sorted(list(not_running))
        for i in range(0, len(sorted_not_running), 10):
            batch = sorted_not_running[i:i+10]
            print(f"   {', '.join(str(slot) for slot in batch)}")
        print()
    else:
        print("✅ All slots are running!\n")

    # Unknown running slots (not owned by wallet)
    if unknown_running:
        print(f"⚠️  Unknown running slots (not in wallet): {len(unknown_running)}")
        sorted_unknown = sorted(list(unknown_running))
        for i in range(0, len(sorted_unknown), 10):
            batch = sorted_unknown[i:i+10]
            print(f"   {', '.join(str(slot) for slot in batch)}")
        print()

    # Potential issues
    if containers_without_screens or screens_without_containers:
        print("⚠️  POTENTIAL ISSUES:")

        if containers_without_screens:
            print(f"   • Containers without screen sessions: {len(containers_without_screens)}")
            sorted_cws = sorted(list(containers_without_screens))
            for i in range(0, len(sorted_cws), 10):
                batch = sorted_cws[i:i+10]
                print(f"     {', '.join(str(slot) for slot in batch)}")

        if screens_without_containers:
            print(f"   • Screen sessions without containers: {len(screens_without_containers)}")
            sorted_swc = sorted(list(screens_without_containers))
            for i in range(0, len(sorted_swc), 10):
                batch = sorted_swc[i:i+10]
                print(f"     {', '.join(str(slot) for slot in batch)}")
        print()

    # Statistics
    print("="*80)
    print(f"Total slots owned: {len(owned_slot_ids)}")
    print(f"Currently running: {len(running_slot_ids)} ({len(running_slot_ids)/len(owned_slot_ids)*100:.1f}%)")
    print(f"Not running: {len(not_running)} ({len(not_running)/len(owned_slot_ids)*100:.1f}%)")
    print("="*80)

    # Exit code based on status
    if not_running:
        sys.exit(1)  # Exit with error if slots are not running
    else:
        sys.exit(0)  # Exit successfully if all slots are running


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
