import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Semaphore

import psutil
from dotenv import load_dotenv
from web3 import Web3

OUTPUT_WORTHY_ENV_VARS = [
    "SOURCE_RPC_URL",
    "SIGNER_ACCOUNT_ADDRESS",
    "WALLET_HOLDER_ADDRESS",
    "TELEGRAM_CHAT_ID",
    "POWERLOOM_RPC_URL",
]

MARKETS_CONFIG_URL = "https://raw.githubusercontent.com/powerloom/curated-datamarkets/master/sources.json"
BDS_MAINNET_MARKET = "BDS_MAINNET_UNISWAPV3"
POWERLOOM_CHAIN = "mainnet"
SOURCE_CHAIN = "ETH"
DEFAULT_POWERLOOM_RPC_URL = "https://rpc-v2.powerloom.network"


def fetch_bds_mainnet_config():
    """Fetch sources.json and return the BDS_MAINNET_UNISWAPV3 market config dict.

    Returns None on failure.
    """
    try:
        req = urllib.request.Request(MARKETS_CONFIG_URL)
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw_data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        print(f"❌ Failed to fetch markets config from {MARKETS_CONFIG_URL}: {e}")
        return None

    # Find MAINNET chain entry
    for chain_entry in raw_data:
        chain_info = chain_entry.get("powerloomChain", {})
        chain_name = chain_info.get("name", "").upper()
        if chain_name != "MAINNET":
            continue
        for market in chain_entry.get("dataMarkets", []):
            if market.get("name", "").upper() == BDS_MAINNET_MARKET:
                # Attach the chain RPC URL for convenience
                market["_powerloom_rpc_url"] = str(
                    chain_info.get("rpcURL", DEFAULT_POWERLOOM_RPC_URL)
                )
                return market

    print(f"❌ Could not find {BDS_MAINNET_MARKET} market in sources.json")
    return None


def get_user_slots(contract_obj, wallet_owner_addr):
    holder_slots = contract_obj.functions.getUserOwnedNodeIds(wallet_owner_addr).call()
    return holder_slots


def build_env_vars(
    market_config: dict,
    source_rpc_url: str,
    signer_addr: str,
    signer_pkey: str,
    slot_id,
    powerloom_rpc_url: str,
    lite_node_branch: str = "master",
    telegram_reporting_url: str = "",
    telegram_chat_id: str = "",
    telegram_message_thread_id: str = "",
    connection_refresh_interval_sec: int = 300,
    env_overrides: dict = None,
) -> dict:
    """Build a complete dict of BDS env vars from market_config (sources.json entry).

    Values from env_overrides (top-level .env) take precedence over defaults.
    """
    if env_overrides is None:
        env_overrides = {}

    def _get(key, default):
        """Return env_overrides value if set, otherwise default."""
        val = env_overrides.get(key)
        return val if val else default

    market_name = market_config.get("name", BDS_MAINNET_MARKET).upper()
    namespace = market_name
    powerloom_chain = POWERLOOM_CHAIN
    source_chain = SOURCE_CHAIN
    full_namespace = f"{powerloom_chain}-{namespace}-{source_chain}"
    docker_network_name = f"snapshotter-lite-v2-{full_namespace}"

    env = {}

    # Core
    env["SOURCE_RPC_URL"] = source_rpc_url
    env["SIGNER_ACCOUNT_ADDRESS"] = signer_addr
    env["SIGNER_ACCOUNT_PRIVATE_KEY"] = signer_pkey
    env["SLOT_ID"] = str(slot_id)
    env["POWERLOOM_RPC_URL"] = powerloom_rpc_url

    # Market-derived (from sources.json)
    env["DATA_MARKET_CONTRACT"] = market_config.get("contractAddress", "")
    env["PROTOCOL_STATE_CONTRACT"] = market_config.get(
        "powerloomProtocolStateContractAddress", ""
    )

    config_section = market_config.get("config", {})
    env["SNAPSHOT_CONFIG_REPO"] = str(config_section.get("repo", ""))
    env["SNAPSHOT_CONFIG_REPO_BRANCH"] = config_section.get("branch", "")
    if config_section.get("commit"):
        env["SNAPSHOT_CONFIG_REPO_COMMIT"] = config_section["commit"]

    compute_section = market_config.get("compute", {})
    env["SNAPSHOTTER_COMPUTE_REPO"] = _get(
        "SNAPSHOTTER_COMPUTE_REPO", str(compute_section.get("repo", ""))
    )
    env["SNAPSHOTTER_COMPUTE_REPO_BRANCH"] = _get(
        "SNAPSHOTTER_COMPUTE_REPO_BRANCH", compute_section.get("branch", "")
    )
    compute_commit = _get(
        "SNAPSHOTTER_COMPUTE_REPO_COMMIT", compute_section.get("commit", "")
    )
    if compute_commit:
        env["SNAPSHOTTER_COMPUTE_REPO_COMMIT"] = compute_commit

    # BDS-specific: IMAGE_TAG derived from lite_node_branch, LOCAL_COLLECTOR_IMAGE_TAG overridable
    env["IMAGE_TAG"] = lite_node_branch
    env["LOCAL_COLLECTOR_IMAGE_TAG"] = _get("LOCAL_COLLECTOR_IMAGE_TAG", "master")
    env["LOCAL_COLLECTOR_PORT"] = _get("LOCAL_COLLECTOR_PORT", "50051")
    env["LOCAL_COLLECTOR_P2P_PORT"] = _get("LOCAL_COLLECTOR_P2P_PORT", "8001")
    env["LOCAL_COLLECTOR_HEALTH_CHECK_PORT"] = _get(
        "LOCAL_COLLECTOR_HEALTH_CHECK_PORT", "8080"
    )

    # P2P Discovery
    bootstrap_nodes = market_config.get("bootstrapNodes", [])
    if bootstrap_nodes:
        env["BOOTSTRAP_NODE_ADDRS"] = ",".join(bootstrap_nodes)
    if market_config.get("rendezvousPoint"):
        env["RENDEZVOUS_POINT"] = market_config["rendezvousPoint"]
    if market_config.get("gossipsubSnapshotSubmissionPrefix"):
        env["GOSSIPSUB_SNAPSHOT_SUBMISSION_PREFIX"] = market_config[
            "gossipsubSnapshotSubmissionPrefix"
        ]
    centralized_seq = market_config.get("centralizedSequencerEnabled")
    if centralized_seq is not None:
        env["CENTRALIZED_SEQUENCER_ENABLED"] = str(centralized_seq).lower()

    # Connection manager (overridable via .env)
    env["CONN_MANAGER_LOW_WATER"] = _get("CONN_MANAGER_LOW_WATER", "100")
    env["CONN_MANAGER_HIGH_WATER"] = _get("CONN_MANAGER_HIGH_WATER", "400")

    # Stream pool (overridable via .env)
    env["MAX_STREAM_POOL_SIZE"] = _get("MAX_STREAM_POOL_SIZE", "2")
    env["MAX_STREAM_QUEUE_SIZE"] = _get("MAX_STREAM_QUEUE_SIZE", "1000")
    env["STREAM_HEALTH_CHECK_TIMEOUT_MS"] = _get(
        "STREAM_HEALTH_CHECK_TIMEOUT_MS", "5000"
    )
    env["STREAM_WRITE_TIMEOUT_MS"] = _get("STREAM_WRITE_TIMEOUT_MS", "5000")
    env["MAX_WRITE_RETRIES"] = _get("MAX_WRITE_RETRIES", "3")
    env["MAX_CONCURRENT_WRITES"] = _get("MAX_CONCURRENT_WRITES", "10")
    env["STREAM_POOL_HEALTH_CHECK_INTERVAL"] = _get(
        "STREAM_POOL_HEALTH_CHECK_INTERVAL", "60000"
    )
    env["WRITE_SEMAPHORE_TIMEOUT_SEC"] = _get("WRITE_SEMAPHORE_TIMEOUT_SEC", "5")

    # Mesh (overridable via .env)
    env["MESH_SUBMISSION_RATE_LIMIT"] = _get("MESH_SUBMISSION_RATE_LIMIT", "100")
    env["MESH_SUBMISSION_BURST_SIZE"] = _get("MESH_SUBMISSION_BURST_SIZE", "200")
    env["MAX_MESH_PUBLISH_GOROUTINES"] = _get("MAX_MESH_PUBLISH_GOROUTINES", "500")
    env["MESH_PUBLISH_QUEUE_SIZE"] = _get("MESH_PUBLISH_QUEUE_SIZE", "1000")

    # Other
    env["DATA_MARKET_IN_REQUEST"] = _get("DATA_MARKET_IN_REQUEST", "true")
    env["PUBLIC_IP"] = _get("PUBLIC_IP", "")
    env["OVERRIDE_DEFAULTS"] = _get("OVERRIDE_DEFAULTS", "true")

    # Naming
    env["NAMESPACE"] = namespace
    env["POWERLOOM_CHAIN"] = powerloom_chain
    env["SOURCE_CHAIN"] = source_chain
    env["FULL_NAMESPACE"] = full_namespace
    env["DOCKER_NETWORK_NAME"] = docker_network_name

    # Optional / Telegram
    env["TELEGRAM_REPORTING_URL"] = telegram_reporting_url
    env["TELEGRAM_CHAT_ID"] = telegram_chat_id
    env["TELEGRAM_MESSAGE_THREAD_ID"] = telegram_message_thread_id
    env["TELEGRAM_NOTIFICATION_COOLDOWN"] = _get(
        "TELEGRAM_NOTIFICATION_COOLDOWN", "300"
    )
    env["CONNECTION_REFRESH_INTERVAL_SEC"] = str(connection_refresh_interval_sec)

    return env


def env_dict_to_string(env_dict: dict) -> str:
    """Serialize an env dict to .env file format."""
    lines = []
    for key, value in env_dict.items():
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def deploy_single_node(
    slot_id: int,
    idx: int,
    market_config: dict,
    full_namespace: str,
    base_dir: str,
    semaphore=None,
    deployment_tracker=None,
    **kwargs,
):
    """Deploy a single node in a thread-safe manner"""
    try:
        # Track deployment start
        if deployment_tracker:
            with deployment_tracker["lock"]:
                deployment_tracker["active"].add(slot_id)

        # Use semaphore to control concurrent deployments if provided
        if semaphore:
            with semaphore:
                result = _deploy_single_node_impl(
                    slot_id,
                    idx,
                    market_config,
                    full_namespace,
                    base_dir,
                    **kwargs,
                )
        else:
            result = _deploy_single_node_impl(
                slot_id,
                idx,
                market_config,
                full_namespace,
                base_dir,
                **kwargs,
            )

        # Track deployment completion
        if deployment_tracker:
            with deployment_tracker["lock"]:
                deployment_tracker["active"].discard(slot_id)
                if result[1] == "success":
                    deployment_tracker["completed"].add(slot_id)
                else:
                    deployment_tracker["failed"].add(slot_id)

        return result
    except Exception as e:
        # Track deployment failure
        if deployment_tracker:
            with deployment_tracker["lock"]:
                deployment_tracker["active"].discard(slot_id)
                deployment_tracker["failed"].add(slot_id)
        return (slot_id, "error", f"Failed to deploy node {slot_id}: {str(e)}")


def _deploy_single_node_impl(
    slot_id: int,
    idx: int,
    market_config: dict,
    full_namespace: str,
    base_dir: str,
    **kwargs,
):
    """Implementation of single node deployment"""
    try:
        print(
            f"🟠 [Worker {threading.current_thread().name}] Starting deployment for slot {slot_id}"
        )

        # Determine collector profile
        if idx > 0:
            collector_profile_string = "--no-collector --no-autoheal-launch"
        else:
            collector_profile_string = ""

        market_name = market_config.get("name", BDS_MAINNET_MARKET).upper()
        repo_name = f"powerloom-{POWERLOOM_CHAIN}-v2-{slot_id}-{market_name}"
        repo_path = os.path.join(base_dir, repo_name)

        # Clean up existing directory
        if os.path.exists(repo_path):
            print(f"Deleting existing dir {repo_name}")
            subprocess.run(["rm", "-rf", repo_path], check=True)

        # Copy template directory
        subprocess.run(
            ["cp", "-R", os.path.join(base_dir, "snapshotter-lite-v2"), repo_path],
            check=True,
        )

        # Generate environment file
        env_vars = build_env_vars(
            market_config=market_config,
            source_rpc_url=kwargs["source_rpc_url"],
            signer_addr=kwargs["signer_addr"],
            signer_pkey=kwargs["signer_pkey"],
            slot_id=slot_id,
            powerloom_rpc_url=kwargs["powerloom_rpc_url"],
            lite_node_branch=kwargs.get("lite_node_branch", "master"),
            telegram_chat_id=kwargs["telegram_chat_id"],
            telegram_message_thread_id=kwargs.get("telegram_message_thread_id", ""),
            telegram_reporting_url=kwargs["telegram_reporting_url"],
            connection_refresh_interval_sec=kwargs["connection_refresh_interval_sec"],
            env_overrides=kwargs.get("env_overrides"),
        )

        env_file_path = os.path.join(repo_path, f".env-{full_namespace}")
        with open(env_file_path, "w+") as f:
            f.write(env_dict_to_string(env_vars))

        # Launch in screen session
        print(
            "--" * 20 + f"Spinning up docker containers for slot {slot_id}" + "--" * 20
        )

        # Build.sh flags: BDS mainnet uses --bds-dsv-mainnet
        build_flags = f"--bds-dsv-mainnet {collector_profile_string} --skip-credential-update --data-market-contract-number 1"

        # Create and launch screen session
        screen_cmd = f"""cd {repo_path} && screen -dmS {repo_name} bash -c './build.sh {build_flags}'"""
        subprocess.run(screen_cmd, shell=True, check=True)

        # Wait and verify container actually starts
        container_started = False
        max_wait_time = 60 if idx == 0 else 30  # First node needs more time
        check_interval = 2
        elapsed = 0

        print(
            f"⏳ Waiting for containers to start for slot {slot_id} (max {max_wait_time}s)..."
        )

        while elapsed < max_wait_time:
            time.sleep(check_interval)
            elapsed += check_interval

            # Check if Docker containers are running for this slot
            container_check = subprocess.run(
                f"docker ps --format '{{{{.Names}}}}' | grep -E 'snapshotter-lite-v2-{slot_id}-{full_namespace}'",
                shell=True,
                capture_output=True,
                text=True,
            )

            if container_check.stdout.strip():
                # Containers found
                container_count = len(container_check.stdout.strip().split("\n"))
                print(f"✅ Found {container_count} container(s) for slot {slot_id}")
                container_started = True
                break

            # Check if screen session is still alive (build might have failed)
            screen_check = subprocess.run(
                f"screen -ls | grep {repo_name}",
                shell=True,
                capture_output=True,
                text=True,
            )

            if not screen_check.stdout.strip() and elapsed > 10:
                # Screen session died after 10 seconds, likely a build failure
                print(f"❌ Build process terminated early for slot {slot_id}")
                break

        if container_started:
            return (
                slot_id,
                "success",
                f"Node {slot_id} deployed successfully with containers running",
            )
        else:
            return (
                slot_id,
                "failed",
                f"Node {slot_id} failed to start containers within {max_wait_time}s",
            )

    except Exception as e:
        return (slot_id, "error", f"Failed to deploy node {slot_id}: {str(e)}")


def run_snapshotter_lite_v2(
    deploy_slots: list,
    market_config: dict,
    **kwargs,
):
    market_name = market_config.get("name", BDS_MAINNET_MARKET).upper()
    full_namespace = f"{POWERLOOM_CHAIN}-{market_name}-{SOURCE_CHAIN}"
    base_dir = os.getcwd()

    # Check if sequential mode is requested
    sequential_mode = kwargs.get("sequential", False)

    if sequential_mode:
        print("📌 Running in sequential mode (parallel deployment disabled)")
        # Original sequential logic
        for idx, slot_id in enumerate(deploy_slots):
            result = deploy_single_node(
                slot_id,
                idx,
                market_config,
                full_namespace,
                base_dir,
                **kwargs,
            )

            if result[1] == "error":
                print(f"❌ Failed to deploy node {slot_id}: {result[2]}")
                continue

            sleep_duration = 30 if idx == 0 else 10
            print(
                f"Sleeping for {sleep_duration} seconds to allow docker containers to spin up..."
            )
            time.sleep(sleep_duration)
        return

    # Parallel deployment mode
    # Create deployment tracker for accurate monitoring
    deployment_tracker = {
        "active": set(),
        "completed": set(),
        "failed": set(),
        "lock": threading.Lock(),
    }

    # Phase 1: Deploy first node with collector
    if deploy_slots:
        print("🚀 Phase 1: Deploying first node with collector service...")
        result = deploy_single_node(
            deploy_slots[0],
            0,
            market_config,
            full_namespace,
            base_dir,
            deployment_tracker=deployment_tracker,
            **kwargs,
        )

        if result[1] == "error":
            print(f"❌ Failed to deploy first node: {result[2]}")
            return

        print(f"✅ First node deployed successfully.")

        # Check if Docker pull lock is released before waiting for collector
        docker_pull_lock = "/tmp/powerloom_docker_pull.lock"
        if os.path.exists(docker_pull_lock):
            print("\n⏳ Docker pull lock detected. Waiting for it to be released...")
            wait_time = 0
            max_wait = 60  # 1 minute max wait
            while os.path.exists(docker_pull_lock) and wait_time < max_wait:
                time.sleep(5)
                wait_time += 5
                print(f"   Still waiting... ({wait_time}s elapsed)")

            if os.path.exists(docker_pull_lock):
                print(
                    "⚠️  Docker pull lock still exists after 60s. Proceeding anyway..."
                )
            else:
                print("✅ Docker pull lock released.")

        print("\n⏳ Waiting 10 seconds for collector initialization...")
        time.sleep(10)

    # For single slot deployment, we're done
    if len(deploy_slots) == 1:
        print("\n✅ Single node deployment completed!")
        return

    # Phase 2: Parallel deployment of remaining nodes
    if len(deploy_slots) > 1:
        print(
            f"\n🚀 Phase 2: Deploying {len(deploy_slots) - 1} remaining nodes in parallel..."
        )

        # Determine number of workers
        cpu_cores = psutil.cpu_count(logical=True)
        default_workers = min(max(4, cpu_cores // 2), 8)
        max_workers = kwargs.get("parallel_workers")

        if max_workers is None:
            max_workers = default_workers
            print(
                f"📊 Using {max_workers} parallel workers (auto-detected based on {cpu_cores} CPU cores)"
            )
        else:
            print(
                f"📊 Using {max_workers} parallel workers (user-specified, detected {cpu_cores} CPU cores)"
            )

        # Deploy remaining nodes in batches with controlled concurrency
        print(
            f"📋 Starting parallel deployment of {len(deploy_slots) - 1} nodes with {max_workers} workers..."
        )

        # Create a semaphore to limit concurrent deployments
        deployment_semaphore = Semaphore(max_workers)

        # Process nodes in batches
        # Batch size is larger than max_workers to keep the pipeline full
        # as some deployments finish faster than others
        remaining_slots = deploy_slots[1:]
        batch_size = (
            max_workers * 3
        )  # Process 3x workers per batch to keep pipeline full
        completed = 0
        total = len(remaining_slots)

        for batch_start in range(0, len(remaining_slots), batch_size):
            batch_end = min(batch_start + batch_size, len(remaining_slots))
            batch = remaining_slots[batch_start:batch_end]
            batch_num = (batch_start // batch_size) + 1
            total_batches = (len(remaining_slots) + batch_size - 1) // batch_size

            print(
                f"\n📦 Processing batch {batch_num}/{total_batches} ({len(batch)} nodes)..."
            )

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Create a mapping of future to slot_id for tracking
                future_to_slot = {}
                for idx_in_batch, (idx, slot_id) in enumerate(enumerate(batch, 1)):
                    actual_idx = batch_start + idx
                    future = executor.submit(
                        deploy_single_node,
                        slot_id,
                        actual_idx + 1,
                        market_config,
                        full_namespace,
                        base_dir,
                        semaphore=deployment_semaphore,
                        deployment_tracker=deployment_tracker,
                        **kwargs,
                    )
                    future_to_slot[future] = slot_id

                # Monitor progress for this batch
                for future in as_completed(future_to_slot, timeout=300):
                    slot_id = future_to_slot[future]
                    try:
                        result = future.result()
                        completed += 1
                        if result[1] == "success":
                            print(f"✅ [{completed}/{total}] {result[2]}")
                        else:
                            print(f"❌ [{completed}/{total}] {result[2]}")
                    except Exception as e:
                        completed += 1
                        print(
                            f"❌ [{completed}/{total}] Node {slot_id} deployment failed with exception: {e}"
                        )

            # Check system state between batches
            if batch_end < len(remaining_slots):
                print(f"\n🔍 Checking system state before next batch...")

                # Wait for Docker pulls to stabilize
                wait_time = 0
                max_wait = 30
                while wait_time < max_wait:
                    docker_pull_lock = "/tmp/powerloom_docker_pull.lock"
                    if os.path.exists(docker_pull_lock):
                        print(f"⏳ Docker pulls in progress, waiting... ({wait_time}s)")
                        time.sleep(5)
                        wait_time += 5
                    else:
                        break

                # Brief pause between batches
                print("⏸️  Pausing 10 seconds before next batch...")
                time.sleep(10)

        # Wait for all deployments to complete using our tracker
        print("\n⏳ Waiting for all background deployments to complete...")

        check_interval = 5
        elapsed = 0
        max_wait_time = 600  # 10 minutes max

        while elapsed < max_wait_time:
            with deployment_tracker["lock"]:
                active_count = len(deployment_tracker["active"])
                completed_count = len(deployment_tracker["completed"])
                failed_count = len(deployment_tracker["failed"])
                total_tracked = completed_count + failed_count

            if active_count == 0 and total_tracked >= len(deploy_slots):
                # All deployments have finished
                print(
                    f"✅ All deployments complete! ({completed_count} successful, {failed_count} failed/delayed)"
                )
                break

            # Show progress
            print(f"🔄 {active_count} deployments still active... ({elapsed}s elapsed)")
            print(
                f"   ✅ Completed: {completed_count}, ⏳ Failed/Delayed: {failed_count}"
            )

            # Show which nodes are still deploying
            if elapsed % 20 == 0 and elapsed > 0 and active_count > 0:
                with deployment_tracker["lock"]:
                    active_nodes = sorted(list(deployment_tracker["active"]))
                print(
                    f"   ℹ️  Active nodes: {', '.join(map(str, active_nodes[:10]))}{' ...' if len(active_nodes) > 10 else ''}"
                )

            time.sleep(check_interval)
            elapsed += check_interval

        if elapsed >= max_wait_time:
            print("⚠️ Timeout waiting for deployments to complete.")
            with deployment_tracker["lock"]:
                if deployment_tracker["active"]:
                    active_nodes = sorted(list(deployment_tracker["active"]))
                    print(
                        f"   Still deploying: {', '.join(map(str, active_nodes[:10]))}{' ...' if len(active_nodes) > 10 else ''}"
                    )

        # Verify deployment status using docker ps with stabilization wait
        print(
            "\n🔍 Verifying deployment status (waiting for containers to stabilize)..."
        )
        try:
            # Get deployment results from the tracker
            completed_slots = deployment_tracker["completed"].copy()
            failed_slots = deployment_tracker["failed"].copy()
            all_deployed = completed_slots.union(failed_slots)

            # Wait for containers to stabilize
            previous_count = 0
            stable_seconds = 0
            check_interval = 3

            while stable_seconds < 10:  # Wait until no new containers for 10 seconds
                # Check running containers
                result = subprocess.run(
                    f"docker ps --format '{{{{.Names}}}}' | grep -E 'snapshotter-lite-v2-[0-9]+-{full_namespace}'",
                    shell=True,
                    capture_output=True,
                    text=True,
                )
                running_containers = set()
                if result.stdout:
                    for line in result.stdout.strip().split("\n"):
                        # Extract slot ID from container name
                        match = re.search(r"snapshotter-lite-v2-(\d+)-", line)
                        if match:
                            running_containers.add(int(match.group(1)))

                current_count = len(running_containers)

                if current_count > previous_count:
                    print(
                        f"   📈 Container count increased: {previous_count} → {current_count}"
                    )
                    previous_count = current_count
                    stable_seconds = 0  # Reset stability counter
                else:
                    stable_seconds += check_interval
                    if stable_seconds < 10:
                        print(
                            f"   ⏳ Container count stable at {current_count} ({stable_seconds}s)..."
                        )

                if stable_seconds < 10:
                    time.sleep(check_interval)

            print(f"   ✅ Container count stabilized at {current_count}")

            # Follow-up check: Revalidate "failed" deployments to see if they started after timeout
            initially_failed = failed_slots.copy()
            delayed_starts = set()
            actually_failed = set()

            if initially_failed and running_containers:
                print(
                    f"\n🔄 Rechecking {len(initially_failed)} deployments marked as failed..."
                )
                for slot_id in initially_failed:
                    if slot_id in running_containers:
                        delayed_starts.add(slot_id)
                    else:
                        actually_failed.add(slot_id)

                if delayed_starts:
                    print(
                        f"   ⏰ {len(delayed_starts)} deployments started after initial timeout"
                    )
                    # Update the tracker to reflect delayed but successful deployments
                    with deployment_tracker["lock"]:
                        for slot_id in delayed_starts:
                            deployment_tracker["failed"].discard(slot_id)
                            deployment_tracker["completed"].add(slot_id)
                    # Update our local copies
                    completed_slots = deployment_tracker["completed"].copy()
                    failed_slots = deployment_tracker["failed"].copy()

            # Now check screen sessions (filter by market namespace)
            market_name = market_config.get("name", BDS_MAINNET_MARKET).upper()
            result = subprocess.run(
                f"screen -ls | grep '{market_name}'",
                shell=True,
                capture_output=True,
                text=True,
            )
            screen_sessions = set()
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    # Extract slot ID from screen name like: 98180.powerloom-mainnet-v2-6568-BDS_MAINNET_UNISWAPV3
                    match = re.search(r"powerloom-[^-]+-[^-]+-(\d+)-", line)
                    if match:
                        screen_sessions.add(int(match.group(1)))

            # Compare
            containers_without_screens = running_containers - screen_sessions
            screens_without_containers = screen_sessions - running_containers
            successful_deployments = running_containers.intersection(screen_sessions)

            print(f"\n📊 Deployment Summary:")

            # Show corrected counts after follow-up check
            if delayed_starts:
                print(
                    f"   ✅ Deployment results (after recheck): {len(completed_slots)} successful, {len(failed_slots)} actually failed"
                )
                print(
                    f"   ⏰ Delayed starts: {len(delayed_starts)} (started after 30s timeout)"
                )
            else:
                print(
                    f"   ✅ Deployment attempts: {len(completed_slots)} successful, {len(failed_slots)} failed"
                )
            print(f"   ✅ Actually running: {len(running_containers)} containers")

            # Check for mismatches
            expected_running = completed_slots - failed_slots
            missing_containers = expected_running - running_containers
            if missing_containers:
                print(
                    f"   ⚠️  Containers that failed to start: {len(missing_containers)}"
                )
                print(
                    f"      Slots: {sorted(list(missing_containers))[:10]}{' ...' if len(missing_containers) > 10 else ''}"
                )

            if delayed_starts:
                print(f"   ⏰ Delayed deployments: {len(delayed_starts)}")
                print(
                    f"      Slots: {sorted(list(delayed_starts))[:10]}{' ...' if len(delayed_starts) > 10 else ''}"
                )

            if failed_slots:
                print(f"   ❌ Actually failed deployments: {len(failed_slots)}")
                print(f"      Slots: {sorted(list(failed_slots))}")

            if screens_without_containers:
                print(
                    f"   ⚠️  Screen sessions without containers: {len(screens_without_containers)}"
                )
                print(
                    f"      Slots: {sorted(list(screens_without_containers))[:10]}{' ...' if len(screens_without_containers) > 10 else ''}"
                )
            if containers_without_screens:
                print(
                    f"   ⚠️  Containers without screen sessions: {len(containers_without_screens)}"
                )
                print(
                    f"      Slots: {sorted(list(containers_without_screens))[:10]}{' ...' if len(containers_without_screens) > 10 else ''}"
                )

            # Show all running containers
            if successful_deployments:
                print(f"\n📺 All running containers:")
                sorted_slots = sorted(list(successful_deployments))
                # Display in columns for better readability
                for i in range(0, len(sorted_slots), 10):
                    batch = sorted_slots[i : i + 10]
                    print(f"   {', '.join(str(slot) for slot in batch)}")

        except Exception as e:
            print(f"Error checking deployment status: {e}")
            pass

        print("\n✅ Deployment process completed!")


def docker_running():
    try:
        # Check if Docker is running
        subprocess.check_output(["docker", "info"])
        return True
    except subprocess.CalledProcessError:
        return False


def main(
    non_interactive: bool = False,
    latest_only: bool = False,
    parallel_workers: int = None,
    sequential: bool = False,
    slot_list: list = None,
    force: bool = False,
):
    # check if Docker is running
    if not docker_running():
        print("🟡 Docker is not running, please start Docker and try again!")
        sys.exit(1)
    # check if .env file exists
    if not os.path.exists(".env"):
        print("🟡 .env file not found, please run bootstrap.sh to create one!")
        sys.exit(1)
    print("🟢 .env file found with following env variables...")
    incomplete_env = False
    with open(".env", "r") as f:
        for line in f:
            # if the line contains any of the OUTPUT_WORTHY_ENV_VARS, print it
            if any(var in line for var in OUTPUT_WORTHY_ENV_VARS):
                print(line.strip())
                if line.strip() == "" or "<" in line.strip() or ">" in line.strip():
                    incomplete_env = True
    if incomplete_env and not non_interactive:
        print(
            "🟡 .env file may be incomplete or corrupted during a previous faulty initialization. Do you want to clear the .env file and re-run ./bootstrap.sh? (y/n)"
        )
        clear_env = input("🫸 ▶︎ Please enter your choice: ")
        if clear_env.lower() == "y":
            os.remove(".env")
            print(
                "🟢 .env file removed, please run ./bootstrap.sh to re-initialize the .env file..."
            )
            sys.exit(0)
    elif incomplete_env and non_interactive:
        print(
            "🟡 .env file may be incomplete or corrupted. Please run bootstrap.sh manually to fix it."
        )
        sys.exit(1)

    load_dotenv(override=True)

    # Fetch BDS mainnet config from sources.json
    print("⚙️ Fetching BDS mainnet market configuration from sources.json...")
    market_config = fetch_bds_mainnet_config()
    if not market_config:
        print("❌ Could not fetch BDS mainnet market config. Exiting.")
        sys.exit(1)
    print(f"🟢 Loaded market config: {market_config.get('name', 'unknown')}")

    # Get PROTOCOL_STATE_CONTRACT from market config (not hardcoded)
    protocol_state_contract_addr = market_config.get(
        "powerloomProtocolStateContractAddress", ""
    )
    if not protocol_state_contract_addr:
        print("❌ PROTOCOL_STATE_CONTRACT not found in market config. Exiting.")
        sys.exit(1)

    # Setup Web3 connections
    wallet_holder_address = os.getenv("WALLET_HOLDER_ADDRESS")
    powerloom_rpc_url = os.getenv("POWERLOOM_RPC_URL")

    if not powerloom_rpc_url:
        powerloom_rpc_url = market_config.get(
            "_powerloom_rpc_url", DEFAULT_POWERLOOM_RPC_URL
        )
        print(
            f"🟡 POWERLOOM_RPC_URL is not set in .env file, using default: {powerloom_rpc_url}"
        )

    # BDS uses master branch
    lite_node_branch = os.getenv("LITE_NODE_BRANCH", "master")
    print(f"🟢 Using lite node branch: {lite_node_branch}")
    local_collector_image_tag = os.getenv("LOCAL_COLLECTOR_IMAGE_TAG", "master")
    print(f"🟢 Using local collector image tag: {local_collector_image_tag}")

    if not wallet_holder_address:
        print("Missing wallet holder address environment variable")
        sys.exit(1)

    # Initialize Web3 and contract connections
    w3 = Web3(Web3.HTTPProvider(powerloom_rpc_url))
    # Load contract ABIs
    with open("snapshotter_cli/utils/abi/ProtocolState.json", "r") as f:
        protocol_state_abi = json.load(f)
    with open("snapshotter_cli/utils/abi/PowerloomNodes.json", "r") as f:
        powerloom_nodes_abi = json.load(f)

    try:
        block_number = w3.eth.get_block_number()
        print(
            f"✅ Successfully fetched the latest block number {block_number}. Your ISP is supported!"
        )
    except Exception as e:
        print(
            f"❌ Failed to fetch the latest block number. Your ISP/VPS region is not supported ⛔️ . Exception: {e}"
        )
        sys.exit(1)

    protocol_state_address = w3.to_checksum_address(protocol_state_contract_addr)
    protocol_state_contract = w3.eth.contract(
        address=protocol_state_address,
        abi=protocol_state_abi,
    )

    slot_contract_address = protocol_state_contract.functions.snapshotterState().call()
    slot_contract_address = w3.to_checksum_address(slot_contract_address)

    print(
        f"🔎 Against protocol state contract {protocol_state_address} found snapshotter state contract {slot_contract_address}"
    )

    # Setup contract instances
    wallet_holder_address = Web3.to_checksum_address(wallet_holder_address)
    slot_contract = w3.eth.contract(
        address=Web3.to_checksum_address(slot_contract_address),
        abi=powerloom_nodes_abi,
    )

    # Get all slots
    slot_ids = get_user_slots(slot_contract, wallet_holder_address)
    if not slot_ids:
        print("No slots found for wallet holder address")
        return

    print(f"Found {len(slot_ids)} slots for wallet holder address")
    print(slot_ids)
    deploy_slots = list()
    # choose range of slots to deploy
    if latest_only:
        # Deploy only the latest (highest) slot
        latest_slot = max(slot_ids)
        deploy_slots = [latest_slot]
        print(f"🟢 Latest-only mode: Deploying only the latest slot {latest_slot}")
    elif slot_list:
        # Deploy specific slots from provided list
        if not force:
            invalid_slots = [slot for slot in slot_list if slot not in slot_ids]
            if invalid_slots:
                print(
                    f"❌ Error: The following slots are not owned by this wallet: {invalid_slots}"
                )
                print(f"Available slots: {slot_ids}")
                sys.exit(1)
        else:
            print("⚠️  Skipping slot ownership validation (--force).")
        deploy_slots = slot_list
        print(f"🟢 Slot list mode: Deploying specified slots {deploy_slots}")
    elif non_interactive:
        deploy_slots = slot_ids
        print("🟢 Non-interactive mode: Deploying all slots")
    else:
        deploy_all_slots = input("☑️ Do you want to deploy all slots? (y/n) ")
        if deploy_all_slots.lower() == "y":
            deploy_slots = slot_ids
        else:
            start_slot = input("🫸 ▶︎ Enter the start slot ID: ")
            end_slot = input("🫸 ▶︎ Enter the end slot ID: ")
            start_slot = int(start_slot)
            end_slot = int(end_slot)
            # find index of start_slot and end_slot in slot_ids
            start_slot_idx = slot_ids.index(start_slot)
            end_slot_idx = slot_ids.index(end_slot)
            deploy_slots = slot_ids[start_slot_idx : end_slot_idx + 1]

    print(f"🎰 Final list of slots to deploy: {deploy_slots}")

    # Display deployment configuration
    print("\n📋 Deployment Configuration:")
    print(f"   • Market: {BDS_MAINNET_MARKET}")
    cpu_cores = psutil.cpu_count(logical=True)
    if parallel_workers is not None:
        print(f"   • Parallel Workers: {parallel_workers} (user-specified)")
    else:
        default_workers = min(max(4, cpu_cores // 2), 8)
        print(
            f"   • Parallel Workers: {default_workers} (auto-detected from {cpu_cores} CPU cores)"
        )

    if sequential:
        print("   • Mode: Sequential (parallel deployment disabled)")
    else:
        print("   • Mode: Parallel")

    print(f"   • Total Slots: {len(deploy_slots)}")
    if not sequential and len(deploy_slots) > 1:
        workers = parallel_workers if parallel_workers is not None else default_workers
        # More realistic estimate:
        # - 10s for first node
        # - Batches of 3x workers processed with some parallelism
        # - Account for delays and Docker operations
        batch_size = workers * 3
        num_batches = ((len(deploy_slots) - 1) + batch_size - 1) // batch_size
        # Assume ~20-30s per batch due to semaphore limiting and Docker operations
        estimated_time = (
            10 + (num_batches * 25) + (num_batches * 10)
        )  # 10s pause between batches
        print(
            f"   • Estimated Time: ~{estimated_time // 60}m {estimated_time % 60}s ({estimated_time} seconds)"
        )
    print()

    if os.path.exists("snapshotter-lite-v2"):
        print(
            "🟡 Previously cloned snapshotter-lite-v2 repo already exists, deleting..."
        )
        os.system("rm -rf snapshotter-lite-v2")
    print(f"⚙️ Cloning snapshotter-lite-v2 repo from {lite_node_branch} branch...")
    os.system(
        f"git clone https://github.com/PowerLoom/snapshotter-lite-v2 --depth 1 --single-branch --branch {lite_node_branch}"
    )

    # CONNECTION_REFRESH_INTERVAL_SEC: default 300, overridable via .env
    connection_refresh_interval = 300
    env_connection_refresh = os.getenv("CONNECTION_REFRESH_INTERVAL_SEC")
    if env_connection_refresh:
        try:
            connection_refresh_interval = int(env_connection_refresh)
            print(
                f"🟢 Using CONNECTION_REFRESH_INTERVAL_SEC from .env: {connection_refresh_interval}"
            )
        except ValueError:
            print(
                f"⚠️ Invalid CONNECTION_REFRESH_INTERVAL_SEC in .env, using default: {connection_refresh_interval}"
            )
    else:
        print(
            f"🟢 Using default CONNECTION_REFRESH_INTERVAL_SEC: {connection_refresh_interval}"
        )

    # Collect all overridable env vars from .env so build_env_vars() can respect them.
    # Any key set in .env takes precedence over the built-in default.
    overridable_keys = [
        "LOCAL_COLLECTOR_IMAGE_TAG",
        "LOCAL_COLLECTOR_PORT",
        "LOCAL_COLLECTOR_P2P_PORT",
        "LOCAL_COLLECTOR_HEALTH_CHECK_PORT",
        "CONN_MANAGER_LOW_WATER",
        "CONN_MANAGER_HIGH_WATER",
        "MAX_STREAM_POOL_SIZE",
        "MAX_STREAM_QUEUE_SIZE",
        "STREAM_HEALTH_CHECK_TIMEOUT_MS",
        "STREAM_WRITE_TIMEOUT_MS",
        "MAX_WRITE_RETRIES",
        "MAX_CONCURRENT_WRITES",
        "STREAM_POOL_HEALTH_CHECK_INTERVAL",
        "WRITE_SEMAPHORE_TIMEOUT_SEC",
        "MESH_SUBMISSION_RATE_LIMIT",
        "MESH_SUBMISSION_BURST_SIZE",
        "MAX_MESH_PUBLISH_GOROUTINES",
        "MESH_PUBLISH_QUEUE_SIZE",
        "DATA_MARKET_IN_REQUEST",
        "PUBLIC_IP",
        "OVERRIDE_DEFAULTS",
        "TELEGRAM_NOTIFICATION_COOLDOWN",
        "SNAPSHOTTER_COMPUTE_REPO",
        "SNAPSHOTTER_COMPUTE_REPO_BRANCH",
        "SNAPSHOTTER_COMPUTE_REPO_COMMIT",
    ]
    env_overrides = {}
    for key in overridable_keys:
        val = os.getenv(key)
        if val is not None:
            env_overrides[key] = val

    run_snapshotter_lite_v2(
        deploy_slots,
        market_config,
        source_rpc_url=os.getenv("SOURCE_RPC_URL"),
        signer_addr=os.getenv("SIGNER_ACCOUNT_ADDRESS"),
        signer_pkey=os.getenv("SIGNER_ACCOUNT_PRIVATE_KEY"),
        powerloom_rpc_url=powerloom_rpc_url,
        lite_node_branch=lite_node_branch,
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        telegram_message_thread_id=os.getenv("TELEGRAM_MESSAGE_THREAD_ID", ""),
        telegram_reporting_url=os.getenv(
            "TELEGRAM_REPORTING_URL", "https://tg-testing.powerloom.io"
        ),
        connection_refresh_interval_sec=connection_refresh_interval,
        env_overrides=env_overrides,
        parallel_workers=parallel_workers,
        sequential=sequential,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Powerloom mainnet multi-node setup (BDS)"
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Deploy all nodes without prompting for confirmation",
    )
    parser.add_argument(
        "--latest-only",
        action="store_true",
        help="Deploy only the latest (highest) slot",
    )
    parser.add_argument(
        "--parallel-workers",
        type=int,
        metavar="N",
        help="Number of parallel workers for deployment (1-8, default: auto-detect based on CPU cores)",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Disable parallel deployment and use sequential mode (backward compatibility)",
    )
    parser.add_argument(
        "--slots",
        type=str,
        metavar="SLOT_IDS",
        help="Comma-separated list of specific slot IDs to deploy (e.g., --slots 1234,5678,9012)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Skip slot ownership validation when using --slots",
    )

    args = parser.parse_args()

    # Validate parallel workers if provided
    if args.parallel_workers is not None:
        if args.parallel_workers < 1 or args.parallel_workers > 8:
            parser.error("--parallel-workers must be between 1 and 8")

    # Parse slot list if provided
    slot_list = None
    if args.slots:
        try:
            # Replace newlines and other whitespace with commas, then split by comma
            normalized = args.slots.replace("\n", ",").replace("\r", ",")
            # Split by comma and filter out empty strings
            slot_list = [
                int(slot.strip()) for slot in normalized.split(",") if slot.strip()
            ]
            if not slot_list:
                parser.error("--slots cannot be empty")
            if len(slot_list) != len(set(slot_list)):
                parser.error("--slots contains duplicate slot IDs")
        except ValueError as e:
            parser.error(
                f"--slots must be a comma-separated list of integers (e.g., 1234,5678,9012). Error: {e}"
            )

    # Validate conflicting options
    if slot_list and args.latest_only:
        parser.error("--slots and --latest-only cannot be used together")
    if slot_list and args.yes:
        parser.error(
            "--slots and --yes cannot be used together (--slots already specifies which slots to deploy)"
        )

    main(
        non_interactive=args.yes,
        latest_only=args.latest_only,
        parallel_workers=args.parallel_workers,
        sequential=args.sequential,
        slot_list=slot_list,
        force=args.force,
    )
