"""CLI Utility Functions"""

import re
import subprocess
import sys

from src import COMMIT_TYPE_NAMES
from src.output import bold

TYPES_PATTERN = '|'.join(COMMIT_TYPE_NAMES)


def clean_commit_message(text: str) -> str:
    """Clean up LLM response to extract just the commit message."""
    lines = text.strip().split('\n')
    start_idx = 0
    for i, line in enumerate(lines):
        if re.match(rf'^[`\s]*({TYPES_PATTERN})[\(!:]', line):
            start_idx = i
            break

    # Find where the actual message ends (cut off diff output, code blocks, etc.)
    JUNK_PATTERNS = re.compile(r'^(diff --git |@@\s|[+-]{3}\s[ab]/|index [0-9a-f]|```)')
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if JUNK_PATTERNS.match(lines[i]):
            end_idx = i
            break

    cleaned = '\n'.join(lines[start_idx:end_idx]).rstrip()
    lines = cleaned.split('\n')
    if lines:
        lines[0] = lines[0].strip('`').strip()

    return '\n'.join(lines)


def copy_to_clipboard(text: str) -> tuple[bool, str]:
    """Copy text to clipboard. Returns (success, failure_reason)."""
    try:
        if sys.platform == 'win32':
            subprocess.run(['clip'], input=text.encode('utf-8'), check=True)
        elif sys.platform == 'darwin':
            subprocess.run(['pbcopy'], input=text.encode('utf-8'), check=True)
        else:
            try:
                subprocess.run(['xclip', '-selection', 'clipboard'], input=text.encode('utf-8'), check=True)
            except FileNotFoundError:
                subprocess.run(['xsel', '--clipboard', '--input'], input=text.encode('utf-8'), check=True)
        return True, ""
    except FileNotFoundError:
        if sys.platform == 'linux':
            return False, "Install xclip or xsel: sudo apt install xclip"
        return False, "No clipboard tool found"
    except (subprocess.CalledProcessError, OSError) as e:
        return False, f"Clipboard command failed: {e}"


def display_options(options: list[str]) -> int | None:
    """Show options and get selection."""
    print()
    for i, opt in enumerate(options, 1):
        print(f"{bold(f'[{i}]')}\n{opt}\n")

    while True:
        try:
            choice = input(f"Select [1-{len(options)}] or (q)uit: ").strip().lower()
            if choice == 'q':
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return idx
        except (ValueError, KeyboardInterrupt, EOFError):
            pass
        print(f"Enter 1-{len(options)} or q")
