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

    cleaned = '\n'.join(lines[start_idx:])
    lines = cleaned.split('\n')
    if lines:
        lines[0] = lines[0].strip('`').strip()

    return '\n'.join(lines)


def copy_to_clipboard(text: str) -> bool:
    """Copy text to clipboard. Works on Windows, Mac, Linux."""
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
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False


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
