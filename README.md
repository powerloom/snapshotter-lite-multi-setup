# Multi node setup for multiple Powerloom Snapshotter Lite: Protocol V2 slot holders on Linux VPS

## 🚀 New: Powerloom Snapshotter CLI

We now offer a powerful command-line interface (CLI) tool that simplifies node management:

### Quick Start with CLI

```bash
# Download the latest binary for your platform
# Linux AMD64
wget https://github.com/PowerLoom/snapshotter-lite-multi-setup/releases/latest/download/powerloom-snapshotter-cli-linux-amd64
chmod +x powerloom-snapshotter-cli-linux-amd64
# Move to PATH - you can use the full name or a shorter alias like 'snapshotter'
sudo mv powerloom-snapshotter-cli-linux-amd64 /usr/local/bin/powerloom-snapshotter-cli
# Or for a shorter command: sudo mv powerloom-snapshotter-cli-linux-amd64 /usr/local/bin/snapshotter

# Start the interactive shell (RECOMMENDED - no startup delays!)
powerloom-snapshotter-cli shell

# Now run commands instantly:
powerloom-snapshotter> configure
powerloom-snapshotter> deploy
powerloom-snapshotter> list
powerloom-snapshotter> status
```

💡 **Why use shell mode?** The CLI has a startup time for each command. Shell mode eliminates this delay, giving you instant command execution!

### Recent CLI Improvements (August 1st 2025)

The CLI has been enhanced with several UX improvements:

- **🎯 Smart Market Selection**:
  - Single-market chains (like MAINNET) auto-select without prompting
  - Multi-market chains show selection UI only when needed
  - Market selection happens before env file loading (fixes auto-selection issue)

- **⚡ Streamlined Configuration**:
  - Powerloom RPC URLs auto-use official defaults - no manual entry needed
  - Fewer prompts for common scenarios
  - Clean URLs without trailing slashes

- **🐧 Linux Compatibility**:
  - Fixed terminal display issues in PyInstaller builds
  - All prompts now display correctly with proper newlines
  - Binaries built on Ubuntu 22.04 for better compatibility

### Key CLI Features

- **🚀 Interactive Shell Mode**: Instant command execution without startup delays (RECOMMENDED!)
- **📋 Integrated Changelog**: View latest changes on shell startup, full changelog with `changelog` command
- **Easy Configuration**: Set up credentials once for each chain/market combination
- **Simple Deployment**: Deploy multiple nodes with a single command
- **Instance Management**: Deploy and monitor snapshotter nodes easily
- **Cross-Platform**: Pre-built binaries for Linux (x86_64, ARM64) and macOS (ARM64)
- **Native ARM64 Builds**: Uses GitHub's native ARM64 runners for 4x faster builds
- **Command History**: Navigate previous commands with arrow keys in shell mode

📖 **[Read the full CLI documentation](CLI_DOCUMENTATION.md)** for detailed usage instructions, examples, and troubleshooting.

📋 **[View the Changelog](CHANGELOG.md)** to see what's new in each release.

---

## Table of Contents

- [Multi node setup for multiple Powerloom Snapshotter Lite: Protocol V2 slot holders on Linux VPS](#multi-node-setup-for-multiple-powerloom-snapshotter-lite-protocol-v2-slot-holders-on-linux-vps)
  - [🚀 New: Powerloom Snapshotter CLI](#-new-powerloom-snapshotter-cli)
  - [Table of Contents](#table-of-contents)
  - [1. Preparation](#1-preparation)
    - [1.1 Run Diagnostics to cleanup old instances](#11-run-diagnostics-to-cleanup-old-instances)
    - [1.2 Choose Installation Method: Manual or Automated](#12-choose-installation-method-manual-or-automated)
      - [1.2.1 Automated Node dependency installation](#121-automated-node-dependency-installation)
      - [1.2.2 Manual Node dependency installation](#122-manual-node-dependency-installation)
  - [2. Setup](#2-setup)
    - [2.1 Initialize Environment](#21-initialize-environment)
    - [2.2 Run the deploy script](#22-run-the-deploy-script)
      - [2.2.0 Deploy script command line flags](#220-deploy-script-command-line-flags)
      - [2.2.1 Deploy a subset of slots](#221-deploy-a-subset-of-slots)
      - [2.2.2 Deploy all slots](#222-deploy-all-slots)
  - [3. Monitoring, diagnostics and cleanup](#3-monitoring-diagnostics-and-cleanup)
    - [3.1 Cleanup\[optional\]](#31-cleanupoptional)
      - [3.1.1 Stop and remove all powerloom containers](#311-stop-and-remove-all-powerloom-containers)
      - [3.1.2 Remove all Docker subnets assigned to the snapshotter-lite containers](#312-remove-all-docker-subnets-assigned-to-the-snapshotter-lite-containers)
      - [3.1.3 Cleanup stale images and networks and cache](#313-cleanup-stale-images-and-networks-and-cache)
  - [4. Case studies](#4-case-studies)
    - [4.1 Deploy subsets of slots with different configs](#41-deploy-subsets-of-slots-with-different-configs)
    - [4.2 Running Slots from Different Wallets on a Single VPS](#42-running-slots-from-different-wallets-on-a-single-vps)
  - [Development and Build Instructions](#development-and-build-instructions)
    - [Building from Source](#building-from-source)
    - [Testing the Build](#testing-the-build)

> [!NOTE]
> This setup is for Lite nodes participating in the latest V2 of Powerloom Protocol with multiple data markets. [Protocol V1 setup](https://github.com/PowerLoom/snapshotter-lite-multi-setup/tree/master) is deprecated and its data markets are archived. Your submission data, rewards on it are finalized and recorded as [announced on Discord](https://discord.com/channels/777248105636560948/1146931631039463484/1242876184509812847).

## 1. Preparation

Clone this repository and change into the repository's directory. All commands will be run within there henceforth.

``` bash
git clone https://github.com/PowerLoom/snapshotter-lite-multi-setup.git snapshotter-lite-multi-setup
cd snapshotter-lite-multi-setup
```

### 1.1 Run Diagnostics to cleanup old instances

First, run the diagnostic tool to check your system and clean up any existing deployments:

``` bash
./diagnose.sh -y
```

> [!NOTE]
> The `-y` flag is recommended to be used as it will skip all the prompts and cleanup existing Powerloom containers and legacy Docker networks without asking for confirmation. If you want to run the script with prompts, you can run it without the `-y` flag.

This will help you:

* Ensure Docker and Docker Compose Availability
* Check if default ports (e.g., `8002`, `50051`) are in use and suggests available alternatives.
* Scan Docker network configurations, listing used subnets and suggesting available ones.
* Check for Powerloom deployment directories and removes them if necessary.
* Detect and terminate active screen sessions related to PowerLoom.
* Stop and remove all Powerloom containers to prevent conflicts.
* Identify and remove unused or legacy Docker networks.

### 1.2 Choose Installation Method: Manual or Automated
To proceed, choose one of the following installation methods:

[1: Automated Node dependency installation](#121-automated-node-dependency-installation)

[2: Manual Node dependency installation](#122-manual-node-dependency-installation)

> [!NOTE]
> Important: You only need to complete one of the methods. After installation, skip to [2. Setup](#2-setup)

#### 1.2.1 Automated Node dependency installation
Run below command to install all node dependences in one go, It might take 5-10 mins depending on VPS specs.

``` bash
./prep.sh
```

This will:

* Detect your operating system (supports Ubuntu, Debian, Fedora, RHEL, CentOS, Rocky Linux, AlmaLinux)
* Update your system packages
* Install Docker and Docker Compose (using apt or yum/dnf as appropriate)
* Install uv (fast Python package manager)
* Install the Powerloom Snapshotter CLI

**Supported Operating Systems:**
- **Debian-based**: Ubuntu, Debian, Raspbian
- **Red Hat-based**: Fedora, RHEL, CentOS, Rocky Linux, AlmaLinux, Oracle Linux

#### 1.2.2 Manual Node dependency installation
Run below commands to install all node dependences manually.

> **Setting Up the Environment**

Install docker and docker compose, Detailed instructions can be found at [Step 3: Setting Up the Environment](https://docs.powerloom.io/docs/build-with-powerloom/snapshotter-node/lite-node-v2/getting-started)


> **Install uv and project dependencies**

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add uv to PATH for current session
export PATH="$HOME/.local/bin:$PATH"

# Add to shell config for future sessions
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Install the Powerloom Snapshotter CLI
./install-uv.sh
```

The install script will:
- Install uv (if not already installed)
- Install the Powerloom Snapshotter CLI globally
- Set up all required dependencies
- Make commands available: `powerloom-snapshotter-cli`, `snapshotter`

## 2. Setup

> [!IMPORTANT]
> **For users migrating from pyenv-based setup or preferring to run without uv:**
>
> If you previously used pyenv with this project, you'll need to ensure uv's Python is used instead:
>
> **Option 1: Use uv run (Recommended)**
> ```bash
> uv run python multi_clone.py
> ```
>
> **Option 2: Install dependencies with pip (without uv)**
> ```bash
> # Install dependencies globally
> pip install -r requirements.txt
> python multi_clone.py
> ```
>
> **Option 3: Activate the virtual environment**
> ```bash
> source .venv/bin/activate
> python multi_clone.py
> deactivate  # when done
> ```
>
> **Option 4: Create a wrapper script**
> ```bash
> echo '#!/bin/bash
> .venv/bin/python multi_clone.py "$@"' > multi_clone.sh
> chmod +x multi_clone.sh
> # Now use: ./multi_clone.sh
> ```
>
> If you're still seeing pyenv Python being used, you may need to temporarily disable pyenv:
> - Comment out pyenv initialization in your shell config (`~/.bashrc` or `~/.zshrc`)
> - Or use the full path: `.venv/bin/python multi_clone.py`

### 2.1 Initialize Environment

Run the bootstrap script to

* Initialize .env file
* re-initialize .env file

``` bash
./bootstrap.sh
```

If you are Initializing .env file for first time it will output like the following:

```
🟡 .env file not found, please follow the instructions below to create one!
creating .env file...
🫸 ▶︎ Please enter the WALLET_HOLDER_ADDRESS:

🫸 ▶︎ Please enter the SOURCE_RPC_URL:

🫸 ▶︎ Please enter the SIGNER_ACCOUNT_ADDRESS:

🫸 ▶︎ Please enter the SIGNER_ACCOUNT_PRIVATE_KEY:

🫸 ▶︎ Please enter the TELEGRAM_CHAT_ID (press enter to skip):

🟢 .env file created successfully!
```

If you already have initilized .env file and trying to re-initilize, you will see output like following

```
🟢 .env file already found to be initialized! If you wish to change any of the values, please backup the .env file at the following prompt.
Do you wish to backup and modify the .env file? (y/n)
y
🟢 .env file backed up to .env.backup.20250210221149
creating .env file...
🫸 ▶︎ Please enter the WALLET_HOLDER_ADDRESS (press enter to keep current value: <wallet-holder-address>):

🫸 ▶︎ Please enter the SOURCE_RPC_URL (press enter to keep current value: <source-rpc-url>):

🫸 ▶︎ Please enter the SIGNER_ACCOUNT_ADDRESS (press enter to keep current value: <signer-account-address>):

🫸 ▶︎ Please enter the SIGNER_ACCOUNT_PRIVATE_KEY (press enter to keep current value: [hidden]):

🫸 ▶︎ Please enter the TELEGRAM_CHAT_ID (press enter to skip) (press enter to keep current value: <telegram-chat-id>):

🟢 .env file created successfully!
```

This will:

* Back up any existing configuration
* Guide you through setting up required variables
* Create a new .env file with your settings
* This step will require you to inform the RPC URL, snapshotter owner wallet address, Signer(Burner) wallet address and signer(burner) wallet private key. When you paste or type the private key, it will look like nothing is typed or pasted, but that´s due to the sensitive information, simply paste and press enter!

### 2.2 Run the deploy script

The deploy script requires Python dependencies. Since we use uv for dependency management, run it with:

```bash
uv run python multi_clone.py
```

> **Note:** The `uv run` prefix ensures all dependencies are available. See the migration note in section 2 if you're coming from a pyenv setup.

#### 2.2.0 Deploy script command line flags

The deploy script supports several command line flags to customize its behavior:

```bash
uv run python multi_clone.py [flags]
```

Available flags:
- `--data-market {1,2}`: Choose the data market (1: AAVEV3, 2: UNISWAPV2)
- `-y, --yes`: Deploy all nodes without prompting for confirmation
- `--latest-only`: Deploy only the latest (highest) slot
- `--use-env-connection-refresh-interval`: Use CONNECTION_REFRESH_INTERVAL_SEC from environment instead of calculating based on slots
- `--parallel-workers N`: Number of parallel workers for deployment (1-8, default: auto-detect based on CPU cores)
- `--sequential`: Disable parallel deployment and use sequential mode (backward compatibility)

#### Parallel Deployment

By default, the script uses parallel deployment to significantly speed up the process:
- Automatically detects CPU cores and uses an optimal number of workers (4-8)
- Deploys the first node with collector service sequentially
- Deploys remaining nodes in parallel batches
- Provides real-time progress tracking

Performance improvements:
- 20 nodes: ~52 seconds (vs 220 seconds sequential)
- 50 nodes: ~90 seconds (vs 520 seconds sequential)
- 100 nodes: ~152 seconds (vs 1020 seconds sequential)

The script automatically calculates an optimal connection refresh interval based on the number of slots being deployed. This calculation ensures stability under load by adjusting the interval linearly.

The `--use-env-connection-refresh-interval` flag modifies this behavior:

- Without the flag (default):
  - Always uses the calculated value
  - If `CONNECTION_REFRESH_INTERVAL_SEC` exists in env but differs from calculated value, warns and uses calculated value

- With the flag:
  - If `CONNECTION_REFRESH_INTERVAL_SEC` exists in env: Uses that value (warns if different from calculated)
  - If `CONNECTION_REFRESH_INTERVAL_SEC` not set: Falls back to calculated value

Example usage:
```bash
# Deploy all slots non-interactively for UNISWAPV2 (uses parallel by default)
uv run python multi_clone.py --data-market 2 -y

# Deploy with specific number of parallel workers
uv run python multi_clone.py --parallel-workers 6 -y

# Deploy using sequential mode (old behavior)
uv run python multi_clone.py --sequential -y

# Deploy only the latest slot
uv run python multi_clone.py --latest-only

# Use environment variable set at shell prompt for connection refresh interval
CONNECTION_REFRESH_INTERVAL_SEC=300 uv run python multi_clone.py --use-env-connection-refresh-interval

# Set the above in .env file and run the script
uv run python multi_clone.py --use-env-connection-refresh-interval
```

> [!IMPORTANT]
> **Local Collector Configuration Behavior**
>
> When deploying multiple slots using this setup script, be aware of the following behavior:
>
> 1. The first deployment determines the local collector's configuration:
>    - The `MAX_STREAM_POOL_SIZE` is calculated based on the total number of slots selected for the first deployment
>    - The `CONNECTION_REFRESH_INTERVAL_SEC` is set based on the number of slots in the first deployment
>
> 2. Subsequent deployments using this script:
>    - Will NOT reconfigure or respawn the existing local collector
>    - Will NOT adjust the `MAX_STREAM_POOL_SIZE` or `CONNECTION_REFRESH_INTERVAL_SEC` values
>    - Will use the configuration set during the first deployment
>
> Therefore, it's recommended to:
> - Plan your initial deployment carefully to include all slots you intend to run
> - If you need to deploy additional slots later with different configurations, consider cleaning up the existing deployment first using the diagnostic script

When you run the deploy script without any flags, it will ask you if you want to deploy all nodes? If you want to [Deploy a subset of slots](#221-deploy-a-subset-of-slots) then press `n` else you want to [Deploy all slots](#222-deploy-all-slots) press `y`.

#### 2.2.1 Deploy a subset of slots

Enter `n` when asked if you want to deploy all slots. Proceed with the begin and end slot IDs for your deployment.

You will see an output like the following:

```
🟢 .env file found with following env variables...
SOURCE_RPC_URL=<your data source rpc url>
SIGNER_ACCOUNT_ADDRESS=<your signer account address>
WALLET_HOLDER_ADDRESS=<your slot holding wallet address>
PROST_RPC_URL=[[https://rpc.powerloom.network\](https://rpc.powerloom.network)](https://rpc.powerloom.network](https://rpc.powerloom.network)) PROST_CHAIN_ID=7865
TELEGRAM_CHAT_ID=<your telegram chat id>
Found n slots for wallet holder address
[xxx1, xxx2, xxx3,xxx4]
☑️ Do you want to deploy all slots? (y/n)n
🫸 ▶︎ Enter the start slot ID: xxx1
🫸 ▶︎ Enter the end slot ID: xxx3 #This will deploy slot xxx1,xxx2,xxx3
```

Choose the data market namespace you want to deploy, UniswapV2 by default.

```
🔍 Select a data market contract (UNISWAPV2 is default):
1. AAVEV3
2. UNISWAPV2

🫸 ▶︎ Please enter your choice (1/2) [default: 2 - UNISWAPV2]: 2
```

And you will see the following output:

```
🟠 Deploying node for slot xxx1 in data market UNISWAPV2
----------------------------------------Spinning up docker containers for slot xxx1----------------------------------------
Sleeping for 30 seconds to allow docker containers to spin up...

...

🟠 Deploying node for slot xxx2 in data market UNISWAPV2
----------------------------------------Spinning up docker containers for slot xxx2----------------------------------------
Sleeping for 10 seconds to allow docker containers to spin up...

...

🟠 Deploying node for slot xxx3 in data market UNISWAPV2
----------------------------------------Spinning up docker containers for slot xxx3----------------------------------------
Sleeping for 10 seconds to allow docker containers to spin up...
```

#### 2.2.2 Deploy all slots

Enter `y` when asked if you want to deploy all slots.

You will see an output like the following:

```
🟢 .env file found with following env variables...
SOURCE_RPC_URL=<your data source rpc url>
SIGNER_ACCOUNT_ADDRESS=<your signer account address>
WALLET_HOLDER_ADDRESS=<your slot holding wallet address>
PROST_RPC_URL=[https://rpc.powerloom.network](https://rpc.powerloom.network)
PROST_CHAIN_ID=7865
TELEGRAM_CHAT_ID=<your telegram chat id>
Found n slots for wallet holder address
[list of slot ids]
☑️ Do you want to deploy all slots? (y/n)n
🫸 ▶︎ Enter the start slot ID: xxx1
🫸 ▶︎ Enter the end slot ID: xxx2
```

Choose the data market namespace you want to deploy, UniswapV2 by default.

```
🔍 Select a data market contract (UNISWAPV2 is default):
1. AAVEV3
2. UNISWAPV2

🫸 ▶︎ Please enter your choice (1/2) [default: 2 - UNISWAPV2]: 2
```

And you will see the following output:

```
🟠 Deploying node for slot xxx1 in data market UNISWAPV2
----------------------------------------Spinning up docker containers for slot xxx1----------------------------------------
Sleeping for 30 seconds to allow docker containers to spin up...

...

🟠 Deploying node for slot xxx2 in data market UNISWAPV2
----------------------------------------Spinning up docker containers for slot xxx2----------------------------------------
Sleeping for 10 seconds to allow docker containers to spin up...
```

## 3\. Monitoring\, diagnostics and cleanup

The multi setup comes bundled with a diagnostic and cleanup script.

``` bash
./diagnose.sh -y
```

> [!NOTE]
> The `-y` flag is recommended to be used as it will skip all the prompts and cleanup existing Powerloom containers and legacy Docker networks without asking for confirmation. If you want to run the script with prompts, you can run it without the `-y` flag.

**Selective Cleanup (New):**

You can now target specific deployments for cleanup:

```bash
# Clean up specific slot ID
./diagnose.sh -y -s 5483

# Clean up specific chain
./diagnose.sh -y -c mainnet

# Clean up specific market
./diagnose.sh -y -m uniswapv2

# Combine filters
./diagnose.sh -y -s 1234 -c devnet -m aavev3
```

The following output may vary depending on whether you have run snapshotter node(s) before this setup or not.

```
./diagnose.sh
🔍 Starting Powerloom Node Diagnostics...

📦 Checking Docker installation...
✅ Docker is installed and running

🐳 Checking docker-compose...
✅ Docker Compose is available

🔌 Checking default ports...
⚠️ Port 8002 is in use
✅ Next available Core API port: 8003
⚠️ Port 50051 is in use
✅ Next available Collector port: 50052

🔍 Checking existing Powerloom containers...
Found existing Powerloom containers:
snapshotter-lite-v2-xxx1-mainnet-UNISWAPV2-ETH
snapshotter-lite-local-collector-xxx1-mainnet-UNISWAPV2-ETH
snapshotter-lite-v2-xxx2-mainnet-UNISWAPV2-ETH
```

If you want to cleanup the existing containers, follow along to the next section

### 3.1 Cleanup[optional]

> [!TIP]
> This is particularly useful if you find your nodes are not running as expected and want a fresh start.

#### 3.1.1 Stop and remove all powerloom containers

If the diagnostic script finds any running containers tagged with `snapshotter-lite`, it will ask you if you want to stop and remove them. The script uses a multi-tiered approach to handle stubborn containers:

1. Graceful stop with 10-second timeout
2. Force kill if graceful stop fails
3. Force remove with fallback strategies

Select `y` at the following prompt and you see some logs like the following:

```
Would you like to stop and remove existing Powerloom containers? (y/n): y

Stopping running containers... (timeout: 10s per container)
Attempting to stop container snapshotter-lite-v2-xxx1-mainnet-UNISWAPV2-ETH...
snapshotter-lite-v2-xxx1-mainnet-UNISWAPV2-ETH
Attempting to stop container snapshotter-lite-local-collector-xxx1-mainnet-UNISWAPV2-ETH...
snapshotter-lite-local-collector-xxx1-mainnet-UNISWAPV2-ETH

Removing containers...
Removing container snapshotter-lite-v2-xxx1-mainnet-UNISWAPV2-ETH...
Removing container snapshotter-lite-local-collector-xxx1-mainnet-UNISWAPV2-ETH...

Removing container snapshotter-lite-v2-xxx2-mainnet-UNISWAPV2-ETH...
```

> [!NOTE]
> The diagnostic script performs cleanup in the proper order: containers first, then screen sessions, networks, and finally deployment directories to avoid conflicts.

#### 3.1.2 Remove all Docker subnets assigned to the snapshotter-lite containers

Enter `y` at the following prompt and you see some logs like the following:

```
Would you like to remove existing Powerloom networks? (y/n): y

Removing networks...
snapshotter-lite-v2-xxx1-mainnet-UNISWAPV2-ETH
snapshotter-lite-v2-xxx2-mainnet-UNISWAPV2-ETH
✅ Networks removed
```

#### 3.1.3 Cleanup stale images and networks and cache

> [!NOTE]
> This is a cleanup step that removes all stale images, networks and cache from Docker. Proceed only if all other attempts at running the node have failed after following our guides.

Enter `y` at the following prompt and you see some logs like the following. Press `y` again at the end to confirm with Docker.

```
Would you like to remove unused Docker resources (only unused images, networks, and cache)? (y/n): y

Removing unused Docker resources...

Running docker network prune...

Running docker system prune...
WARNING! This will remove:
  - all stopped containers
  - all networks not used by at least one container
  - all images without at least one container associated to them
  - all build cache

Are you sure you want to continue? [y/N] y

Deleted Images:
untagged: [ghcr.io/powerloom/snapshotter-lite-v2:latest](http://ghcr.io/powerloom/snapshotter-lite-v2:latest)
untagged: [ghcr.io/powerloom/snapshotter-lite-v2@sha256:15e05050bbf1473a3b4345a188c44bb37fb343f89d24f9ce731e3c3df190ec98](http://ghcr.io/powerloom/snapshotter-lite-v2@sha256:15e05050bbf1473a3b4345a188c44bb37fb343f89d24f9ce731e3c3df190ec98)
deleted: sha256:33d723744d4cb306c9be663247464f497698682fb0d577290831114b825bc84a

Total reclaimed space: 1.614GB
✅ Cleanup complete

✅ Diagnostic check complete
```

If you encounter any issues, please contact us on [discord](https://discord.com/invite/powerloom).

## 4. Case studies

### 4.1 Deploy subsets of slots with different configs

Meet Bob, The Architect of Chaos. Bob has five Powerloom slots, but he's got an itch to make things complicated—deploying three nodes each with a different RPC and two nodes sharing a single RPC. Here's how he pulls it off:

1. Bob logs into his VPS and follows [Preparation](#1-preparation).
2. When initializing the environment (by `./bootstrap.sh`), he inputs all the necessary slot info and sets **RPC1**.
3. Bob then runs the deploy script: (by `uv run python multi_clone.py`). Since he's deploying a subset of slots, he follows [Deploy a subset of slots](#221-deploy-a-subset-of-slots) and sets the **start slot** and **end slot** to **slot1**. BOOM! **Slot1 is live.**
4. Bob repeats the process for **slot2** using **RPC2** and deploys **slot2** using the same method.
5. He does the same for **RPC3** to deploy **slot3**.
6. Now for the final trick, Bob wants **slot4 and slot5** to share **RPC4**. He reinitializes the env variables by (by `./bootstrap.sh`), and when deploying(by uv run python multi\_clone.py), he sets **start slot to slot4 and end slot to slot5**.

BOOM! Bob did it. **Three slots running on three different RPCs and two slots sharing a single RPC.** Mission accomplished. 🎉

### 4.2 Running Slots from Different Wallets on a Single VPS

Meet Alice, the queen of efficiency. Unlike Bob, who enjoys juggling multiple RPCs, Alice faces a different challenge. Her four Powerloom slots are spread across three wallets, but she wants them all running smoothly on a single VPS. Here's how she pulls it off:
She clones `X(#of wallets)` multiscript directories, each with different destination directory name.

1. Alice logs into her VPS and follows [Preparation](#1-preparation), She then clones the repository three times, assigning a unique destination directory name to each clone.
2. Now, she [Setup](#2-setup) two nodes from **Wallet 1** on a single RPC. When initializing the environment (by `./bootstrap.sh`), she inputs all the necessary for wallet1 info and sets **RPC1**.
3. Alice then runs the deploy script: (by `uv run python multi_clone.py`). Since she's deploying a subset of slots, she follows [Deploy a subset of slots](#221-deploy-a-subset-of-slots) and sets the **start slot** to **slot1** and **end slot** to **slot2**. BOOM! **Slot1 and slot2 is live.**
4. Alice then navigates to the second repository (by `cd <directory-name>`), initializes the environment (by `./bootstrap.sh`) and inputs all the necessary info for wallet2 and sets **RPC1**. She then deploys node from wallet 2 by running deploy script: (by `uv run python multi_clone.py`) and follows [Deploy a subset of slots](#221-deploy-a-subset-of-slots)Finally, she repeats the same process for **Slot 3** from **Wallet 3**, just as she did for Slot 2.

BOOM! Alice did it. **Four slots from three different wallet running on single VPS.** Mission accomplished. 🎉


## Development and Build Instructions

### Building from Source

There are two ways to install and use the powerloom-snapshotter-cli:

1. **Using the Package (Recommended for Users)**

```bash
# Install using uv (recommended)
uv tool install powerloom-snapshotter-cli

# Or install using pipx
pipx install powerloom-snapshotter-cli
```

2. **Building from Source (For Development)**

Prerequisites:
- uv (Python package manager)

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/PowerLoom/snapshotter-lite-multi-setup.git
cd snapshotter-lite-multi-setup

# Set up development environment
./setup-uv.sh

# Or manually:
# Pin Python version and install dependencies
uv python pin 3.12
uv sync

# Build the package
uv build
```

This will create:
- A wheel file in `dist/powerloom_snapshotter_cli-X.Y.Z-py3-none-any.whl`
- A source distribution in `dist/powerloom_snapshotter_cli-X.Y.Z.tar.gz`

### Testing the Build

```bash
# Install the CLI globally with uv (use --force to update existing installation)
uv tool install --force --from dist/powerloom_snapshotter_cli-X.Y.Z-py3-none-any.whl powerloom-snapshotter-cli

# Or for development, install in editable mode
uv tool install --editable --from . powerloom-snapshotter-cli

# Test the CLI
powerloom-snapshotter-cli --help
```

### Development Workflow

```bash
# Run CLI during development
uv run powerloom-snapshotter-cli --help

# Run tests
uv run pytest

# Format code
./scripts/lint.sh fix

# Check code quality
./scripts/lint.sh
```

### Development Guidelines

For code quality and pre-commit setup, please see [README_PRECOMMIT.md](README_PRECOMMIT.md)

## Recent Improvements (2025-08-04)

### Enhanced Shell Mode
- **Market Selection**: Shell mode now properly fetches and displays all available markets for the selected chain (e.g., both AAVEV3 and UNISWAPV2 for DEVNET)
- **Smart Auto-selection**: Single-market chains (like MAINNET) automatically select the only available market without prompting
- **Better Defaults**: MAINNET is now the default chain, ETH-MAINNET is the default source chain
- **Case-insensitive Input**: Chain and market names now accept mixed case input (e.g., "mainnet", "Mainnet", "MAINNET" all work)

### Streamlined Configuration
- **Powerloom RPC URL**: Automatically uses defaults from sources.json without prompting
- **Single Market Auto-selection**: Both `deploy` and `configure` commands auto-select when only one market is available
- **Fixed Terminal Display**: Resolved issues with prompts appearing on the same line in Linux PyInstaller builds

### Build and Compatibility
- **Linux Binary Naming**: Changed from `x86_64` to `amd64` for consistency
- **glibc Compatibility**: Binaries now built on Ubuntu 22.04 for broader compatibility
- **ARM64 Native Builds**: Using GitHub's native ARM64 runners for faster builds
