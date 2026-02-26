# Changelog

All notable changes to the Powerloom Snapshotter CLI and setup tools will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [v0.3.1] - 2026-02-26

### Fixed
- **Slot ownership validation for `--slot`/`--slots` flags (#101)** - Deploy command now validates that explicitly provided slot IDs are owned by the wallet before deploying, matching the validation already present in the interactive path and legacy `multi_clone.py`. Previously, unowned slots passed via flags would silently attempt deployment and fail.

### Improved
- **Configure command prompt UX** - Replaced confusing empty `()` brackets with explicit hints: `(required)`, `(optional, leave blank to skip)`, `(current: value, press Enter to keep)` when overwriting, and `(default: value, press Enter to use)` for built-in defaults. Makes first-time setup vs reconfiguration clearer.

## [v0.3.0] - 2026-02-24

### Added

- **CLI `check` command** - New command to compare wallet-owned slots against running containers, showing running/not-running status, detecting orphaned sessions, and providing deployment hints
- **--slots flag (multi_clone.py)** - Deploy specific slots via comma-separated list (e.g., `--slots 1234,5678,9012`)
- **check_slots.py script** - Monitor deployment health by comparing owned slots vs running containers with detailed statistics
- **BDS DSV Market Support** - Added support for `BDS_DEVNET_ALPHA_UNISWAPV3` and `BDS_MAINNET_UNISWAPV3` markets in deployment and CLI
- **Commit ID Support** - Added support for config and compute packages commit IDs from sources.json in environment variables
- **Powerloom RPC URL Configuration** - Added Powerloom RPC URL prompt and selection process in configure command
- **P2P Discovery and Connection Manager** - Added P2P Discovery and connection manager configuration for BDS-DSV deployments
- **Centralized Sequencer Submission Switch** - Added support for centralized sequencer submission switch in local collector
- **Active Profile Support in Deployment** - Added active profile support for environment configuration in deployment

### Changed
- **BDS DSV Mainnet** - CLI and lite node use `--bds-dsv-mainnet` for mainnet BDS; and `--bds-dsv-devnet` for devnet BDS. Mainnet market is `BDS_MAINNET_UNISWAPV3` with P2P prefix/rendezvous `dsv-mainnet-bds`. Devnet market is `BDS_DEVNET_ALPHA_UNISWAPV3` with P2P prefix/rendezvous `dsv-devnet-alpha`.
- **Markets Config URL** - Updated MARKETS_CONFIG_URL to point to master branch of curated-datamarkets repository
- **Gossipsub Configuration** - Refactored to parse gossipsub configuration from market config instead of hardcoded values
- **Local Collector Repository Cloning** - Removed redundant local collector repository cloning from deployment logic (handled by lite node setup)

### Fixed
- **Configure Command Env Var Preservation** - Fixed configure command to preserve custom environment variables that are not part of the template
- **Image Tags for BDS Markets** - Fixed enforcement of experimental image tags for LOCAL_COLLECTOR and IMAGE in BDS deployments
- **Boolean Environment Variables** - Fixed normalization of boolean environment variables to lowercase for consistency
- **POWERLOOM_CHAIN Variable** - Fixed POWERLOOM_CHAIN variable assignment in deployment
- **Failed deployments display** - "Actually failed deployments" now shows complete list instead of truncating to first 10
- **Profile set-default to "default"** - Fixed bug where `profile set-default default` didn't properly switch to the default profile in shell mode


## [v0.2.0] - 2025-10-27

### Added
- **Multi-Profile Support (#90)** - Manage multiple wallet configurations for the same chain+market combination
- **Profile commands** - New `profile` command group: `create`, `list`, `copy`, `delete`, `set-default`, `show`, `export`, `import`
- **Profile parameter** - Added `--profile` flag to `configure`, `deploy`, and `identity` commands
- **Shell mode profile display** - Shows active profile in prompt: `[profile-name] powerloom-snapshotter>`
- **POWERLOOM_PROFILE** - Environment variable support for profile selection

### Changed
- **Configuration storage** - Configs now stored in `~/.powerloom-snapshotter-cli/profiles/{profile_name}/` with automatic migration of existing configs to "default" profile
- **Shell mode auto-injection** - Commands automatically use active profile when `--profile` not specified

### Fixed
- **Shell mode --help flag** - Fixed `--help` flag handling for command groups (like `profile --help`) in shell mode
- **Shell mode readline history** - Fixed extra character display when using arrow keys for command history navigation

## [v0.1.6] - 2025-10-09

### Added
- **Selective cleanup filters (#89)** - Added `--slot-id`, `--chain`, and `--market` filter options to `diagnose` command (CLI, shell mode, and legacy `diagnose.sh` script) for targeted cleanup of specific deployments instead of cleaning everything at once

### Fixed
- **Configure overwrite prompt (#88)** - Fixed issue where pressing any key other than 'y' or 'n' would abort configuration. Now re-prompts for valid input instead of aborting
- **OVERRIDE_DEFAULTS environment variable** - Fixed multi_clone.py not passing OVERRIDE_DEFAULTS from .env to lite v2 deployments
- **Slot deployment logic** - Refactored interactive mode slot selection to check for 'y' first, making the code flow more intuitive and maintainable

## [v0.1.5] - 2025-08-31

### Fixed
- **PyInstaller binary runtime error** - Fixed FileNotFoundError when running binary by including `pyproject.toml` in the PyInstaller bundle and handling the bundled file path correctly

## [v0.1.4] - 2025-08-27

### Added
- **Telegram message thread ID support** - Added `TELEGRAM_MESSAGE_THREAD_ID` configuration option for organizing notifications into specific threads within Telegram chats
- **Conditional Telegram cooldown prompt** - Only asks for notification cooldown when Telegram chat ID is provided

### Fixed
- **LITE_NODE_BRANCH configuration (#79)** - CLI now properly reads and uses LITE_NODE_BRANCH from environment configuration when cloning snapshotter-lite-v2
- **Configuration value preservation (#76)** - Technical parameters now properly preserve existing values when updating configuration

### Changed
- **Streamlined configuration** - Removed prompts for TELEGRAM_REPORTING_URL, MAX_STREAM_POOL_SIZE, and CONNECTION_REFRESH_INTERVAL_SEC
- **Smart changelog display** - Shows "What's New" only once per version update to reduce notification fatigue
- **Enhanced markdown formatting** - Bold text in changelog now renders properly in terminal output
- **Connection refresh interval default** - Changed from 75 to 60 seconds for better performance

### Improved
- **Configuration UX** - Reduced from 9+ prompts to 6-7 essential ones, auto-setting technical parameters with smart defaults
- **prep.sh installation** - Added `screen` package to prerequisites for apt-based systems
- **install-uv.sh PATH guidance** - Added clear instructions for sourcing uv environment after installation

## [v0.1.3] - 2025-08-09

### Added
- **Changelog support** - Display latest changes on shell startup and via `changelog` command
- **CLI --changelog flag** - View changelog directly from command line without entering shell mode

### Fixed
- **Critical: ENV file case mismatch (#72)** - CLI now generates `.env-mainnet-UNISWAPV2-ETH` instead of `.env-MAINNET-UNISWAPV2-ETH` to match `build.sh` expectations
- **Devnet deployments** - Added missing `--devnet` flag when deploying to devnet
- **Data market contract numbers** - Added `--data-market-contract-number` flag with proper mapping (1=AAVEV3, 2=UNISWAPV2)

### Changed
- **Chain selection order** - Mainnet now appears first in all selection prompts
- **Chain name display** - Chains now display as "Mainnet" and "Devnet" (title case) instead of all caps
- **Default market number** - Changed default from 2 to 1 for unknown markets (more conservative approach)
- **UI consistency** - Configure command now uses the same Panel-based UI as deploy command for chain selection

### Enhanced
- **Shell mode** - Applied chain ordering and title case improvements to interactive shell

## [v0.1.2] - 2025-08-08

### Fixed
- Character removal in wallet address input on Linux - lowercase 'b' characters were being incorrectly removed

### Added
- Git commit info to version display for better tracking

## [v0.1.1] - 2025-08-05

### Fixed
- Terminal display issues in Linux CLI builds - prompts now display correctly with proper newlines
- Deployment market selection flow - market selection now happens before env file loading
- Linux binary glibc compatibility - builds now use Ubuntu 22.04 for better compatibility

### Changed
- GitHub Actions workflow updated to use Ubuntu 22.04
- Standardized architecture naming to `amd64` for consistency

### Enhanced
- Streamlined configuration UX - auto-uses defaults from sources.json, no RPC URL prompt needed
- Auto-selection for single-market chains

## [v0.1.0] - 2025-07-23

### Added
- Initial release of `powerloom-snapshotter-cli`
- Interactive shell mode to eliminate ~6-7 second startup delays
- Configure command for credential management
- Deploy command for node deployment
- Status command for monitoring containers
- List command for viewing deployments
- Logs command for viewing container logs
- Identity management commands
- Support for multiple chains (MAINNET, DEVNET)
- Support for multiple markets (UNISWAPV2, AAVEV3)

### Legacy Support
- Maintained backward compatibility with traditional scripts:
  - `bootstrap.sh` for configuration
  - `multi_clone.py` for deployment
  - `diagnose.sh` for system diagnostics
  - `prep.sh` for automated system preparation

---

[v0.3.1]: https://github.com/powerloom/snapshotter-lite-multi-setup/releases/tag/v0.3.1
[v0.3.0]: https://github.com/powerloom/snapshotter-lite-multi-setup/releases/tag/v0.3.0
[v0.2.0]: https://github.com/powerloom/snapshotter-lite-multi-setup/releases/tag/v0.2.0
[v0.1.6]: https://github.com/powerloom/snapshotter-lite-multi-setup/releases/tag/v0.1.6
[v0.1.5]: https://github.com/powerloom/snapshotter-lite-multi-setup/releases/tag/v0.1.5
[v0.1.4]: https://github.com/powerloom/snapshotter-lite-multi-setup/releases/tag/v0.1.4
[v0.1.3]: https://github.com/powerloom/snapshotter-lite-multi-setup/releases/tag/v0.1.3
[v0.1.2]: https://github.com/powerloom/snapshotter-lite-multi-setup/releases/tag/v0.1.2
[v0.1.1]: https://github.com/powerloom/snapshotter-lite-multi-setup/releases/tag/v0.1.1
[v0.1.0]: https://github.com/powerloom/snapshotter-lite-multi-setup/releases/tag/v0.1.0
