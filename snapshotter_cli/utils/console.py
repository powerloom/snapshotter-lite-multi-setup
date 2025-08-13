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
