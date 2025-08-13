# Powerloom Snapshotter CLI

A powerful command-line interface for deploying and managing Powerloom Snapshotter nodes. Simplifies the process of running multiple snapshotter instances across different chains and data markets.

## Features

- 🚀 **Interactive Shell Mode** - Eliminates startup delays for multiple commands
- 📦 **Multi-Instance Management** - Deploy and manage multiple snapshotter nodes
- 🔧 **Easy Configuration** - Store credentials per chain/market combination  
- 🔍 **Built-in Diagnostics** - Check system health and troubleshoot issues
- 🐳 **Docker Integration** - Automated container and network management
- 🔐 **Secure Credential Storage** - Namespaced environment configurations

## Installation

```bash
# Install using pip
pip install powerloom-snapshotter-cli

# Install using pipx (recommended)
pipx install powerloom-snapshotter-cli
```

## Quick Start

### Interactive Shell (Recommended)

```bash
# Start interactive shell for faster command execution
powerloom-snapshotter-cli shell

# In shell mode:
powerloom-snapshotter> configure
powerloom-snapshotter> deploy
powerloom-snapshotter> status
```

### Direct Commands

```bash
# Configure credentials for a chain/market
powerloom-snapshotter-cli configure --env mainnet --market uniswapv2

# Deploy a snapshotter instance
powerloom-snapshotter-cli deploy

# Check status of running instances
powerloom-snapshotter-cli status

# View detailed status
powerloom-snapshotter-cli status --env mainnet --market uniswapv2
```

## Available Commands

- `configure` - Set up chain and market-specific credentials
- `deploy` - Deploy a new snapshotter instance
- `status` - View status of deployed instances
- `list` - Display available chains and data markets
- `diagnose` - Run system diagnostics
- `identity` - Manage multiple configurations
- `shell` - Start interactive mode

## Command Aliases

The CLI is available through multiple aliases:
- `powerloom-snapshotter-cli` (full name)
- `snapshotter` (short)

## Supported Chains & Markets

- **Mainnet**: Ethereum mainnet data markets
- **Devnet**: Development network for testing
- Multiple data markets including UniswapV2, AaveV3, and more

## Requirements

- Python 3.12 or higher
- Docker and Docker Compose
- Linux or macOS (Windows support via WSL)

## Documentation

- [Full Documentation](https://github.com/powerloom/snapshotter-lite-multi-setup/blob/master/CLI_DOCUMENTATION.md)
- [GitHub Repository](https://github.com/powerloom/snapshotter-lite-multi-setup)
- [Powerloom Website](https://powerloom.io)

## License

MIT License - see [LICENSE](https://github.com/powerloom/snapshotter-lite-multi-setup/blob/master/LICENSE) for details.

## Support

- [Report Issues](https://github.com/powerloom/snapshotter-lite-multi-setup/issues)
- [Discord Community](https://discord.gg/powerloom)
