"""CLI Utility Functions"""

import os
import re
import subprocess
import sys
import tempfile

from src import COMMIT_TYPE_NAMES
from src.output import bold, dim, info, colorize_commit_type

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


def _format_option(message: str, option_num: int) -> str:
    """Format a single option with colored type and clear visual hierarchy."""
    colored = colorize_commit_type(message)
    lines = colored.split('\n')

    # Build formatted output with colored option number
    parts = [f"{info(f'[{option_num}]')} {bold(lines[0])}"]

    # Add body lines with proper indentation
    body_lines = [line for line in lines[1:] if line.strip()]
    if body_lines:
        parts.append("")  # Blank line between subject and body
        for line in body_lines:
            # Dim the bullet character for visual hierarchy
            if line.strip().startswith('-'):
                line = line.replace('-', dim('-'), 1)
            parts.append(f"    {line}")

    return '\n'.join(parts)


def display_options(options: list[str]) -> int | None:
    """Show options and get selection with formatted display."""
    print()
    for i, opt in enumerate(options, 1):
        print(_format_option(opt, i))
        if i < len(options):
            print()  # Blank line
            print(dim("    · · ·"))  # Subtle separator
            print()  # Blank line

    print()  # Space before prompt
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


def edit_message(message: str) -> str | None:
    """Open message in user's editor. Returns edited text or None on failure."""
    editor = os.environ.get('VISUAL') or os.environ.get('EDITOR')
    if not editor:
        editor = 'notepad' if sys.platform == 'win32' else 'vi'

    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.gitcommit', delete=False, encoding='utf-8')
    try:
        tmp.write(message)
        tmp.close()
        subprocess.run([editor, tmp.name], check=True)
        with open(tmp.name, 'r', encoding='utf-8') as f:
            edited = f.read().strip()
        return edited if edited else None
    except (subprocess.CalledProcessError, OSError):
        return None
    finally:
        try:
            os.unlink(tmp.name)
        except OSError as e:
            # Log to stderr so temp files don't silently accumulate
            print(f"Warning: Could not delete temp file {tmp.name}: {e}", file=sys.stderr)
