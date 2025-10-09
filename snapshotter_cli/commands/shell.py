import os
import shlex
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import typer
from rich.console import Console
from rich.pager import Pager
from rich.panel import Panel
from rich.text import Text
from typer.main import get_command

from snapshotter_cli import get_version_string
from snapshotter_cli.utils.changelog import display_changelog, get_latest_changes
from snapshotter_cli.utils.console import Prompt, console
from snapshotter_cli.utils.deployment import CONFIG_DIR

try:
    import readline

    HAS_READLINE = True

    # Check if we're using libedit (macOS) vs GNU readline
    # libedit requires different binding syntax for tab completion
    USING_LIBEDIT = False
    if hasattr(readline, "__doc__") and readline.__doc__:
        if "libedit" in readline.__doc__:
            USING_LIBEDIT = True
except ImportError:
    HAS_READLINE = False
    USING_LIBEDIT = False

# Global variables for autocomplete
COMMANDS = {}
CURRENT_COMMAND_OPTIONS = []


def command_completer(text: str, state: int) -> Optional[str]:
    """Autocomplete function for readline.

    This function is called by readline to generate completions.
    """
    # Get the full line and cursor position
    line = readline.get_line_buffer()
    cursor_pos = readline.get_endidx()

    # Parse what's been typed so far
    parts = line[:cursor_pos].split()

    # If we're completing the first word (command name)
    if len(parts) <= 1:
        # Get all available commands (regular + special)
        all_commands = list(COMMANDS.keys()) + ["help", "exit", "quit", "clear", "cls"]
        matches = [cmd for cmd in all_commands if cmd.startswith(text)]

        if state < len(matches):
            return matches[state]
        return None

    # If we're completing options or subcommands for a command
    cmd_name = parts[0]
    if cmd_name in COMMANDS:
        click_cmd = COMMANDS[cmd_name]

        # Check if this is a command group (has subcommands)
        if hasattr(click_cmd, "commands"):
            # We're dealing with a command group
            if len(parts) == 2:
                # Complete subcommand names
                subcommands = list(click_cmd.commands.keys())
                matches = [sc for sc in subcommands if sc.startswith(text)]

                if state < len(matches):
                    return matches[state]
            elif len(parts) > 2:
                # Complete options for the subcommand
                subcmd_name = parts[1]
                if subcmd_name in click_cmd.commands:
                    subcmd = click_cmd.commands[subcmd_name]
                    options = []
                    if hasattr(subcmd, "params"):
                        for param in subcmd.params:
                            if hasattr(param, "opts"):
                                options.extend(param.opts)

                    matches = [opt for opt in options if opt.startswith(text)]
                    if state < len(matches):
                        return matches[state]
        else:
            # Regular command - complete options
            options = []
            if hasattr(click_cmd, "params"):
                for param in click_cmd.params:
                    if hasattr(param, "opts"):
                        options.extend(param.opts)

            # Filter options that match the current text
            matches = [opt for opt in options if opt.startswith(text)]

            if state < len(matches):
                return matches[state]

    return None


def parse_command(command_line: str) -> tuple[str, List[str]]:
    """Parse a command line into command name and arguments."""
    try:
        parts = shlex.split(command_line)
        if not parts:
            return "", []
        return parts[0], parts[1:]
    except ValueError as e:
        console.print(f"[red]Error parsing command: {e}[/red]")
        return "", []


def get_missing_parameters(
    click_cmd, args: List[str], parent_ctx: Optional[typer.Context] = None
) -> List[str]:
    """Interactively prompt for missing required parameters."""
    # Parse what parameters were already provided
    provided_params = {}
    i = 0
    while i < len(args):
        if args[i].startswith("-"):
            # This is a flag
            param_name = args[i].lstrip("-")
            if i + 1 < len(args) and not args[i + 1].startswith("-"):
                # Next item is the value
                provided_params[param_name] = args[i + 1]
                i += 2
            else:
                # Flag without value (boolean flag)
                provided_params[param_name] = True
                i += 1
        else:
            i += 1

    # Collect missing required parameters
    collected_args = list(args)

    if hasattr(click_cmd, "params"):
        for param in click_cmd.params:
            if hasattr(param, "required") and param.required:
                # Check if this parameter was provided
                param_names = getattr(param, "opts", [])
                provided = False

                for opt in param_names:
                    opt_name = opt.lstrip("-")
                    if opt_name in provided_params:
                        provided = True
                        break

                if not provided:
                    # This is a missing required parameter, prompt for it
                    param_name = param.name
                    param_help = getattr(param, "help", "") or f"Enter {param_name}"

                    # Special handling for known parameters
                    if param_name == "source_chain" or param_name == "source-chain":
                        # Auto-select ETH-MAINNET without prompting
                        value = "ETH-MAINNET"
                        console.print(
                            f"✅ Auto-selected source chain: [bold cyan]{value}[/bold cyan]"
                        )
                    elif param_name == "slot_id" or param_name == "slot-id":
                        # Prompt for slot ID (no special handling needed, just get input)
                        value = Prompt.ask(f"\n[cyan]{param_help}[/cyan]")
                    elif param_name == "chain":
                        # Get available chains from CLI context
                        available_chains = ["MAINNET", "DEVNET"]
                        if parent_ctx and hasattr(parent_ctx, "obj") and parent_ctx.obj:
                            cli_context = parent_ctx.obj
                            if hasattr(cli_context, "available_environments"):
                                # Sort chains to prioritize MAINNET first
                                available_chains = sorted(
                                    cli_context.available_environments,
                                    key=lambda x: (x.upper() != "MAINNET", x.upper()),
                                )

                        # Show available chains
                        console.print(
                            f"\nAvailable chains: {', '.join([c.title() for c in available_chains])}"
                        )

                        while True:
                            chain_input = Prompt.ask(
                                f"[cyan]{param_help}[/cyan]", default="MAINNET"
                            )

                            # Check case-insensitive match
                            chain_upper = chain_input.upper()
                            if chain_upper in available_chains:
                                value = chain_upper
                                break

                            console.print(
                                f"❌ Invalid selection. Please choose from: {', '.join([c.title() for c in available_chains])}",
                                style="red",
                            )
                    elif param_name == "market":
                        # Try to get available markets based on selected chain
                        available_markets = None
                        selected_chain = None

                        # Check if chain was provided in args or already prompted
                        for i, arg in enumerate(collected_args):
                            if arg in ["--chain", "-c"] and i + 1 < len(collected_args):
                                selected_chain = collected_args[i + 1].upper()
                                break

                        # Get available markets from CLI context
                        if (
                            parent_ctx
                            and hasattr(parent_ctx, "obj")
                            and parent_ctx.obj
                            and selected_chain
                        ):
                            cli_context = parent_ctx.obj
                            if (
                                hasattr(cli_context, "chain_markets_map")
                                and selected_chain in cli_context.chain_markets_map
                            ):
                                chain_data = cli_context.chain_markets_map[
                                    selected_chain
                                ]
                                if hasattr(chain_data, "markets"):
                                    available_markets = sorted(
                                        chain_data.markets.keys()
                                    )

                        if available_markets:
                            # Auto-select if only one market is available
                            if len(available_markets) == 1:
                                value = available_markets[0]
                                console.print(
                                    f"✅ Auto-selected the only available market: [bold cyan]{value}[/bold cyan]"
                                )
                            else:
                                # Show available markets
                                console.print(
                                    f"\nAvailable markets for {selected_chain}:"
                                )
                                for i, market in enumerate(available_markets, 1):
                                    console.print(
                                        f"  [bold green]{i}.[/] [cyan]{market}[/]"
                                    )

                                while True:
                                    market_input = Prompt.ask(
                                        "👉 Select data market (number or name)"
                                    )
                                    if market_input.isdigit():
                                        idx = int(market_input) - 1
                                        if 0 <= idx < len(available_markets):
                                            value = available_markets[idx]
                                            break
                                    elif market_input.upper() in available_markets:
                                        value = market_input.upper()
                                        break
                                    console.print(
                                        "❌ Invalid selection. Please try again.",
                                        style="red",
                                    )
                        else:
                            # Fallback to default if no markets found
                            value = Prompt.ask(
                                f"\n[cyan]{param_help}[/cyan]", default="UNISWAPV2"
                            )
                    else:
                        # Generic prompt
                        value = Prompt.ask(f"\n[cyan]{param_help}[/cyan]")

                    # Add the parameter to args
                    # Use the first option name (usually the long form)
                    if param_names:
                        collected_args.extend([param_names[0], value])

    return collected_args


def run_shell(app: typer.Typer, parent_ctx: typer.Context):
    """Run an interactive shell for the CLI."""
    global COMMANDS

    # Setup readline history and autocomplete if available
    history_file = None
    if HAS_READLINE:
        # Setup history
        try:
            history_file = os.path.join(
                tempfile.gettempdir(), ".powerloom_shell_history"
            )
            readline.read_history_file(history_file)
        except (FileNotFoundError, OSError, IOError):
            # History file doesn't exist yet or can't be accessed
            history_file = None
        except Exception:
            # Any other readline errors - disable history
            history_file = None

        try:
            readline.set_history_length(1000)
        except Exception:
            # If setting history length fails, continue without it
            pass

        # Setup autocomplete
        readline.set_completer(command_completer)

        # Configure readline bindings based on implementation
        if USING_LIBEDIT:
            # libedit (macOS) requires this specific binding for tab completion
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            # GNU readline (Linux) works best with standard tab binding
            # Avoid 'bind' command on Linux as it can cause input issues (e.g., lowercase 'b' removal)
            readline.parse_and_bind("tab: complete")

    # Build the welcome message
    welcome_msg = f"[bold green]Powerloom Snapshotter CLI v{get_version_string()} - Interactive Mode[/bold green]\n"
    welcome_msg += "Type 'help' for available commands, 'exit' or 'quit' to leave.\n"
    if HAS_READLINE:
        welcome_msg += (
            "Use Tab for command completion, Ctrl+C to cancel current command."
        )
    else:
        welcome_msg += "Use Ctrl+C to cancel current command."

    console.print(
        Panel.fit(
            welcome_msg,
            border_style="green",
        )
    )

    # Show latest changes if available (only once per version)
    # Get the full version string including commit hash
    full_version = get_version_string()

    # Check if we should show the changelog
    version_file = CONFIG_DIR / ".last_shown_changelog_version"
    should_show_changelog = True

    try:
        if version_file.exists():
            last_shown_version = version_file.read_text().strip()
            if last_shown_version == full_version:
                should_show_changelog = False
    except Exception:
        # If we can't read the file, show the changelog
        pass

    if should_show_changelog:
        latest_changes = get_latest_changes()
        if latest_changes:
            console.print(
                Panel(
                    latest_changes,
                    title="[bold blue]What's New[/bold blue]",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

            # Save the current version as shown
            try:
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                version_file.write_text(full_version)
            except Exception:
                # Silently fail if we can't write the file
                pass

    # Build command map from the app
    commands = {}

    # Get the Click command group from Typer app
    click_group = get_command(app)

    # Iterate through registered commands
    if hasattr(click_group, "commands"):
        for name in click_group.commands:
            if name != "shell":  # Don't include shell itself
                commands[name] = click_group.commands[name]

    # Add special commands
    special_commands = {
        "help": lambda: show_help(commands),
        "exit": lambda: sys.exit(0),
        "quit": lambda: sys.exit(0),
        "clear": lambda: console.clear(),
        "cls": lambda: console.clear(),
        "changelog": display_changelog,
    }

    # Update global COMMANDS to include both regular and special commands for autocomplete
    COMMANDS = {**commands, **{name: None for name in special_commands}}

    while True:
        try:
            # Get user input with readline support
            if HAS_READLINE:
                try:
                    command_line = input("\npowerloom-snapshotter> ").strip()
                except EOFError:
                    console.print("\n[yellow]Goodbye![/yellow]")
                    break
            else:
                command_line = Prompt.ask(
                    "\n[bold cyan]powerloom-snapshotter[/bold cyan]", default=""
                ).strip()

            if not command_line:
                continue

            # Parse command
            cmd_name, args = parse_command(command_line)

            # Handle special commands
            if cmd_name in special_commands:
                special_commands[cmd_name]()
                continue

            # Handle regular commands
            if cmd_name in commands:
                try:
                    # Get the Click command
                    click_cmd = commands[cmd_name]

                    # Check if this is a command group (has subcommands)
                    if hasattr(click_cmd, "commands"):
                        # This is a command group, check if first arg is a valid subcommand
                        potential_subcmd = args[0] if args else None
                        if potential_subcmd and potential_subcmd in click_cmd.commands:
                            # We have a valid subcommand, include it in the context
                            pass  # Let the normal flow handle it
                        else:
                            # Invalid or missing subcommand
                            if not potential_subcmd:
                                console.print(
                                    f"[red]Error: Command '{cmd_name}' requires a subcommand[/red]"
                                )
                            else:
                                console.print(
                                    f"[red]Error: '{potential_subcmd}' is not a valid subcommand for '{cmd_name}'[/red]"
                                )
                            console.print(
                                f"Available subcommands: {', '.join(click_cmd.commands.keys())}"
                            )
                            continue

                    # Create a new context for this command
                    click_group = get_command(app)

                    # Use Click's Context to invoke the command
                    # Create a fresh context that includes the parent's obj (CLIContext)
                    with click_group.make_context(
                        "powerloom-snapshotter", [cmd_name] + args
                    ) as cmd_ctx:
                        # Copy the parent context's obj if it exists
                        if hasattr(parent_ctx, "obj") and parent_ctx.obj:
                            cmd_ctx.obj = parent_ctx.obj
                        click_group.invoke(cmd_ctx)

                except click.exceptions.Exit:
                    # Normal exit from command
                    pass
                except typer.Exit:
                    # Commands might call typer.Exit, which we should catch
                    pass
                except click.exceptions.UsageError as e:
                    # Handle missing required parameters more gracefully
                    error_msg = str(e)
                    if "Missing" in error_msg and "parameter" in error_msg:
                        # In REPL mode, interactively collect missing parameters
                        console.print(
                            f"[yellow]Missing required parameters. Let's fill them in:[/yellow]"
                        )

                        try:
                            # Determine which command/subcommand we're dealing with
                            if (
                                hasattr(click_cmd, "commands")
                                and args
                                and args[0] in click_cmd.commands
                            ):
                                # This is a subcommand
                                target_cmd = click_cmd.commands[args[0]]
                                new_args = get_missing_parameters(
                                    target_cmd, args[1:], parent_ctx
                                )
                                final_args = [args[0]] + new_args
                            else:
                                # Regular command
                                final_args = get_missing_parameters(
                                    click_cmd, args, parent_ctx
                                )

                            # Try executing again with collected parameters
                            with click_group.make_context(
                                "powerloom-snapshotter", [cmd_name] + final_args
                            ) as retry_ctx:
                                if hasattr(parent_ctx, "obj") and parent_ctx.obj:
                                    retry_ctx.obj = parent_ctx.obj
                                click_group.invoke(retry_ctx)

                        except click.exceptions.UsageError as retry_error:
                            console.print(f"[red]Error: {retry_error}[/red]")
                        except (click.exceptions.Exit, SystemExit):
                            # Command completed successfully
                            pass
                        except KeyboardInterrupt:
                            console.print("\n[yellow]Command cancelled[/yellow]")
                        except Exception as ex:
                            console.print(f"[red]Error: {ex}[/red]")
                    else:
                        console.print(f"[red]Usage error: {e}[/red]")
                except Exception as e:
                    console.print(f"[red]Error executing command: {e}[/red]")
            else:
                console.print(f"[red]Unknown command: {cmd_name}[/red]")
                console.print("Type 'help' for available commands.")

        except KeyboardInterrupt:
            console.print("\n[yellow]Use 'exit' or 'quit' to leave the shell.[/yellow]")
        except EOFError:
            # Handle Ctrl+D
            console.print("\n[yellow]Goodbye![/yellow]")
            break

    # Save history on exit
    if HAS_READLINE and history_file:
        try:
            readline.write_history_file(history_file)
        except:
            pass  # Ignore errors saving history


def show_help(commands: dict):
    """Show available commands."""
    console.print("\n[bold]Available Commands:[/bold]")

    # Regular commands
    for name, command in sorted(commands.items()):
        # Get help text from Click command
        help_text = (
            getattr(command, "help", None)
            or getattr(command, "short_help", None)
            or "No description available"
        )
        # Get first line of help text
        help_line = (
            str(help_text).split("\n")[0] if help_text else "No description available"
        )
        console.print(f"  [cyan]{name:<15}[/cyan] {help_line}")

    # Special commands
    console.print("\n[bold]Special Commands:[/bold]")
    console.print("  [cyan]help[/cyan]           Show this help message")
    console.print("  [cyan]changelog[/cyan]      Show the full changelog")
    console.print("  [cyan]clear/cls[/cyan]      Clear the screen")
    console.print("  [cyan]exit/quit[/cyan]      Exit the shell")
    console.print(
        "\n[dim]Tip: You can use shell syntax like quotes for arguments with spaces.[/dim]"
    )


def shell_command(ctx: typer.Context, app: typer.Typer):
    """Start an interactive shell session."""
    # Get the parent context which has the loaded config
    parent_ctx = ctx.parent if ctx.parent else ctx
    run_shell(app, parent_ctx)
