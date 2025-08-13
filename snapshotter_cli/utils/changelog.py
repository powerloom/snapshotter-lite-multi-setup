"""Changelog utilities for displaying and formatting CHANGELOG.md content."""

import importlib.resources as resources
import os
import re
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console

from snapshotter_cli.utils.console import console


def find_changelog_path() -> Optional[Path]:
    """Find the CHANGELOG.md file in various locations.

    Returns:
        Path to the changelog file if found, None otherwise.
    """
    possible_paths = []

    # Check if running from PyInstaller bundle
    if getattr(sys, "frozen", False):
        # Running from PyInstaller bundle
        bundle_dir = Path(sys._MEIPASS)
        possible_paths.append(bundle_dir / "CHANGELOG.md")
    else:
        # Check pip package installation location
        try:
            # For Python 3.9+
            if hasattr(resources, "files"):
                package_files = resources.files("snapshotter_cli")
                possible_paths.append(package_files / "CHANGELOG.md")
        except ImportError:
            pass

    # Also check regular locations
    possible_paths.extend(
        [
            Path("CHANGELOG.md"),  # Current directory
            Path(__file__).parent.parent
            / "CHANGELOG.md",  # Pip installed package location
            Path(__file__).parent.parent.parent
            / "CHANGELOG.md",  # Relative to this file (dev)
        ]
    )

    for path in possible_paths:
        if path.exists():
            return path

    return None


def format_changelog_content(content: str) -> str:
    """Format markdown changelog content for Rich display.

    Args:
        content: Raw markdown content from CHANGELOG.md

    Returns:
        Formatted content string for Rich console display
    """
    formatted_lines = []
    lines = content.split("\n")

    # Add header
    formatted_lines.append("[bold cyan]📋 Changelog[/bold cyan]")
    formatted_lines.append(
        "[dim]Use arrow keys or Page Up/Down to scroll, 'q' to quit[/dim]\n"
    )

    for line in lines:
        if line.startswith("# "):
            # Main header
            formatted_lines.append(f"[bold magenta]{line[2:]}[/bold magenta]")
        elif line.startswith("## "):
            # Version headers - handle brackets without escaping issues
            version_line = line[3:]  # Remove "## "
            # Replace brackets with unicode lookalikes to avoid Rich markup interpretation
            version_line = version_line.replace("[", "［").replace("]", "］")
            formatted_lines.append(f"\n[bold cyan]{version_line}[/bold cyan]")
        elif line.startswith("### "):
            # Section headers
            formatted_lines.append(f"\n[bold yellow]{line[4:]}[/bold yellow]")
        elif line.startswith("---"):
            # Horizontal rule - skip it or show as separator
            formatted_lines.append("\n" + "─" * 40)
        elif line.startswith("[") and "]: " in line:
            # Reference-style link definitions (e.g., [v0.1.3]: https://...)
            # Format these nicely or skip them
            parts = line.split("]: ", 1)
            if len(parts) == 2:
                version = parts[0][1:]  # Remove leading [
                url = parts[1]
                formatted_lines.append(f"[dim]  {version}: {url}[/dim]")
            else:
                formatted_lines.append(line)
        elif line.startswith("- "):
            # Bullet points - handle inline bold text
            bullet_content = line[2:]
            # Replace **text** with [bold]text[/bold]
            bullet_content = re.sub(
                r"\*\*([^*]+)\*\*", r"[bold]\1[/bold]", bullet_content
            )
            formatted_lines.append(f"  • {bullet_content}")
        elif line.startswith("  - "):
            # Sub-bullet points - handle inline bold text
            sub_bullet_content = line[4:]
            sub_bullet_content = re.sub(
                r"\*\*([^*]+)\*\*", r"[bold]\1[/bold]", sub_bullet_content
            )
            formatted_lines.append(f"    ◦ {sub_bullet_content}")
        elif line.startswith("**") and line.endswith("**") and len(line) > 4:
            # Bold text (entire line)
            formatted_lines.append(f"[bold]{line[2:-2]}[/bold]")
        elif line.strip():
            # Regular lines - also handle inline bold text
            formatted_line = re.sub(r"\*\*([^*]+)\*\*", r"[bold]\1[/bold]", line)
            formatted_lines.append(formatted_line)
        else:
            formatted_lines.append("")

    return "\n".join(formatted_lines)


def display_changelog():
    """Display the full changelog with formatted markdown.

    This function finds the CHANGELOG.md file, formats it, and displays it
    using Rich's pager for scrollable content.
    """
    try:
        # Check if we're in a PyInstaller bundle
        is_frozen = getattr(sys, "frozen", False)

        # For Linux binaries, we need special handling to ensure colors work
        if is_frozen and sys.platform.startswith("linux"):
            # Force terminal detection for Linux binaries
            # Use TERM environment variable to help Rich detect capabilities
            if "TERM" not in os.environ:
                os.environ["TERM"] = "xterm-256color"

            # Create console with explicit settings for better Linux binary compatibility
            display_console = Console(
                force_terminal=True,
                force_interactive=True,
                color_system="256",
                legacy_windows=False,
            )
        else:
            # Standard console for other environments
            display_console = console

        changelog_path = find_changelog_path()

        if changelog_path:
            with open(changelog_path, "r") as f:
                content = f.read()

            formatted_content = format_changelog_content(content)

            # For frozen Linux binaries, avoid pager which can cause color issues
            if is_frozen and sys.platform.startswith("linux"):
                # Print without pager for Linux binaries
                display_console.print(formatted_content)
                display_console.print("\n[dim]End of changelog[/dim]")
            else:
                # Use pager for other environments
                with display_console.pager(styles=True):
                    display_console.print(formatted_content)
        else:
            display_console.print(
                "[yellow]Changelog file not found. View online at:[/yellow]"
            )
            display_console.print(
                "https://github.com/powerloom/snapshotter-lite-multi-setup/blob/master/CHANGELOG.md"
            )
    except Exception as e:
        # Always use the standard console for error messages
        console.print(f"[red]Error reading changelog: {e}[/red]")


def get_latest_changes() -> Optional[str]:
    """Extract the latest changes from CHANGELOG.md file.

    Returns:
        Formatted string of latest changes for shell startup display, or None if not found.
    """
    try:
        changelog_path = find_changelog_path()

        if not changelog_path:
            return None

        with open(changelog_path, "r") as f:
            content = f.read()

        # Parse the changelog to get the latest unreleased section or latest release
        lines = content.split("\n")
        in_unreleased = False
        in_latest_release = False
        changes = []
        version_count = 0
        has_unreleased_content = False

        for line in lines:
            # Check for version headers
            if line.startswith("## ["):
                version_count += 1
                if "Unreleased" in line:
                    in_unreleased = True
                    in_latest_release = False
                    # Don't add header yet, wait to see if there's content
                elif version_count == 1 and not in_unreleased:
                    # First version header and it's not Unreleased - this is the latest release
                    in_latest_release = True
                    version_info = line.replace("## ", "").strip()
                    # Replace brackets with unicode lookalikes to avoid Rich markup issues
                    version_info = version_info.replace("[", "［").replace("]", "］")
                    changes = [
                        f"[bold cyan]📋 Latest Release: {version_info}[/bold cyan]\n"
                    ]
                elif version_count == 2:  # Second version header
                    if in_unreleased and not has_unreleased_content:
                        # Unreleased was empty, show this version instead
                        in_unreleased = False
                        in_latest_release = True
                        version_info = line.replace("## ", "").strip()
                        # Replace brackets with unicode lookalikes to avoid Rich markup issues
                        version_info = version_info.replace("[", "［").replace(
                            "]", "］"
                        )
                        changes = [
                            f"[bold cyan]📋 Latest Release: {version_info}[/bold cyan]\n"
                        ]
                    else:
                        break  # Stop after unreleased section or first release
                elif version_count > 2:
                    break  # Stop after first version section
            elif in_unreleased and line.strip() and not line.startswith("## "):
                # Found content in unreleased section
                if not has_unreleased_content:
                    # Add the header now that we know there's content
                    changes.insert(
                        0, f"[bold cyan]📋 Latest Changes (Unreleased)[/bold cyan]\n"
                    )
                    has_unreleased_content = True
                # Convert markdown headers to rich formatting
                if line.startswith("### "):
                    formatted_line = line.replace("### ", "\n[bold yellow]")
                    formatted_line += "[/bold yellow]"
                    changes.append(formatted_line)
                elif line.startswith("- "):
                    # Format bullet points and handle inline bold text
                    bullet_content = line[2:]
                    bullet_content = re.sub(
                        r"\*\*([^*]+)\*\*", r"[bold]\1[/bold]", bullet_content
                    )
                    changes.append(f"  • {bullet_content}")
                elif line.strip() and not line.startswith("#"):
                    changes.append(line)
            elif in_latest_release and line.strip():
                # Convert markdown headers to rich formatting
                if line.startswith("### "):
                    formatted_line = line.replace("### ", "\n[bold yellow]")
                    formatted_line += "[/bold yellow]"
                    changes.append(formatted_line)
                elif line.startswith("- "):
                    # Format bullet points and handle inline bold text
                    bullet_content = line[2:]
                    bullet_content = re.sub(
                        r"\*\*([^*]+)\*\*", r"[bold]\1[/bold]", bullet_content
                    )
                    changes.append(f"  • {bullet_content}")
                elif line.strip() and not line.startswith("#"):
                    changes.append(line)

        if changes:
            result = "\n".join(changes[:20])  # Limit to first 20 lines
            result += '\n\n[dim]Type "changelog" to see the full changelog[/dim]'
            return result

        return None

    except Exception:
        # Silently fail if we can't read the changelog
        return None
