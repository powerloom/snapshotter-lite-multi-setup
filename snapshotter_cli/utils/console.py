"""
Console utilities for consistent terminal handling across the CLI.
Fixes newline issues in PyInstaller Linux builds.
"""

import getpass
import re
import sys
from typing import Optional

from rich.console import Console as RichConsole
from rich.prompt import Prompt as RichPrompt


def config_prompt(
    label: str,
    *,
    current_value: str = "",
    default_value: Optional[str] = None,
    optional: bool = False,
    password: bool = False,
) -> str:
    """
    Prompt for config values with clear first-time vs overwrite wording.
    Avoids confusing empty () and uses explicit [current: x] / [default: x] / [required] hints.

    - current_value: existing saved value (overwriting config). Empty = first-time.
    - default_value: built-in default when no current value (e.g. "8001", Powerloom RPC URL).
    - optional: if True, user can leave blank.
    """
    has_current = bool(current_value and current_value.strip())
    has_builtin_default = default_value is not None and default_value != ""

    # Use parentheses (not brackets) so hints survive Rich markup stripping in frozen builds
    if password and has_current:
        hint = "(current: set, press Enter to keep)"
    elif has_current:
        # Truncate long values for display
        display = (
            current_value if len(current_value) <= 50 else current_value[:47] + "..."
        )
        hint = f"(current: {display}, press Enter to keep)"
    elif has_builtin_default:
        display = (
            default_value if len(default_value) <= 60 else default_value[:57] + "..."
        )
        hint = f"(default: {display}, press Enter to use)"
    elif optional:
        hint = "(optional, leave blank to skip)"
    else:
        hint = "(required)"

    prompt_text = f"{label} {hint}"
    if password and has_current:
        effective_default = "(hidden)"  # configure.py maps this back to existing_key
    else:
        effective_default = current_value if has_current else (default_value or "")

    return Prompt.ask(
        prompt_text,
        default=effective_default,
        show_default=False,  # We embed the hint in the prompt text
        password=password,
    )


def get_console() -> RichConsole:
    """
    Get a properly configured Rich Console instance.

    For PyInstaller frozen builds, forces standard terminal mode
    to fix newline handling issues on Linux.
    """
    if getattr(sys, "frozen", False):
        # Force standard terminal for PyInstaller builds
        return RichConsole(force_terminal=True, legacy_windows=False)
    else:
        return RichConsole()


# Global console instance
console = get_console()


class Prompt(RichPrompt):
    """Custom Prompt class that uses our configured console."""

    @classmethod
    def ask(
        cls,
        prompt: str = "",
        *,
        console: Optional[RichConsole] = None,
        password: bool = False,
        choices: Optional[list] = None,
        show_default: bool = True,
        show_choices: bool = True,
        default: str = ...,
        stream: Optional[object] = None,
    ) -> str:
        """Override ask to use our configured console by default."""
        if console is None:
            console = globals()["console"]  # Use our global console instance

        # For PyInstaller builds on Linux, use a simpler approach
        if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
            # Strip Rich markup tags for plain text display
            plain_prompt = re.sub(r"\[.*?\]", "", prompt)

            # Print prompt with default value on the same line
            prompt_text = plain_prompt
            if show_default and default is not ... and default != "":
                prompt_text = f"{plain_prompt} ({default})"

            # Use standard input() to avoid Rich's terminal handling issues
            if password:
                print(prompt_text, end="", flush=True)
                value = getpass.getpass(" ")
            else:
                value = input(f"{prompt_text}: ").strip()

            # Return default if empty input
            if not value and default is not ...:
                return str(default)
            return value

        # Use normal Rich prompt for non-frozen builds
        return super().ask(
            prompt,
            console=console,
            password=password,
            choices=choices,
            show_default=show_default,
            show_choices=show_choices,
            default=default,
            stream=stream,
        )
