"""Terminal Output Formatting Package"""

import re
import sys
import os
import threading
import time


class Colors:
    """ANSI escape codes for terminal colors."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    CYAN = '\033[36m'
    MAGENTA = '\033[35m'


def _supports_color() -> bool:
    if os.environ.get('NO_COLOR'):
        return False
    if os.environ.get('FORCE_COLOR'):
        return True
    if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
        return False
    if sys.platform == 'win32':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return True


def _supports_unicode() -> bool:
    if sys.platform == 'win32':
        try:
            '✓'.encode(sys.stdout.encoding or 'utf-8')
            return True
        except (UnicodeEncodeError, LookupError):
            return False
    return True


COLORS_ENABLED = _supports_color()
UNICODE_ENABLED = _supports_unicode()

CHECK = '✓' if UNICODE_ENABLED else '[OK]'
CROSS = '✗' if UNICODE_ENABLED else '[X]'
ARROW = '→' if UNICODE_ENABLED else '->'
BULLET = '•' if UNICODE_ENABLED else '*'


def _colorize(text: str, *codes: str) -> str:
    if not COLORS_ENABLED:
        return text
    return f"{''.join(codes)}{text}{Colors.RESET}"


def success(text: str) -> str:
    return _colorize(text, Colors.GREEN)


def error(text: str) -> str:
    return _colorize(text, Colors.RED)


def warning(text: str) -> str:
    return _colorize(text, Colors.YELLOW)


def info(text: str) -> str:
    return _colorize(text, Colors.CYAN)


def dim(text: str) -> str:
    return _colorize(text, Colors.DIM)


def bold(text: str) -> str:
    return _colorize(text, Colors.BOLD)


def highlight(text: str) -> str:
    return _colorize(text, Colors.MAGENTA)


def print_success(message: str) -> None:
    print(f"{success(CHECK)} {message}")


def print_error(message: str) -> None:
    print(f"{error(CROSS)} {error(message)}", file=sys.stderr)


def print_warning(message: str) -> None:
    print(f"{warning('⚠')} {warning(message)}" if UNICODE_ENABLED else f"[!] {message}")


def print_box(text: str) -> None:
    import shutil
    import textwrap

    term_width = shutil.get_terminal_size((80, 24)).columns
    # Box chrome takes 4 chars: "│ " + " │"
    max_width = max(int(term_width * 0.8), 60) - 4

    lines = text.split('\n')
    wrapped_lines = []
    for line in lines:
        if len(line) > max_width:
            indent = '  ' if line.startswith('- ') else ''
            wrapped_lines.extend(textwrap.wrap(line, width=max_width, subsequent_indent=indent))
        else:
            wrapped_lines.append(line)

    content_width = max(len(line) for line in wrapped_lines)

    if UNICODE_ENABLED:
        top = f'┌─{"─" * content_width}─┐'
        bottom = f'└─{"─" * content_width}─┘'
        side = '│'
    else:
        top = f'+-{"-" * content_width}-+'
        bottom = f'+-{"-" * content_width}-+'
        side = '|'

    print(dim(top))
    for line in wrapped_lines:
        padding = ' ' * (content_width - len(line))
        print(f"{dim(side)} {line}{padding} {dim(side)}")
    print(dim(bottom))


COMMIT_TYPE_COLORS = {
    'feat': Colors.GREEN,
    'fix': Colors.RED,
    'refactor': Colors.YELLOW,
    'docs': Colors.CYAN,
    'test': Colors.MAGENTA,
    'perf': Colors.GREEN,
    'chore': Colors.DIM,
    'style': Colors.DIM,
    'ci': Colors.CYAN,
    'build': Colors.CYAN,
}


def colorize_commit_type(message: str) -> str:
    """Color the commit type prefix on the first line of a commit message."""
    if not COLORS_ENABLED:
        return message
    lines = message.split('\n')
    if not lines:
        return message
    match = re.match(r'^(\w+)(\([^)]*\))?(!?:)', lines[0])
    if match:
        commit_type = match.group(1)
        color = COMMIT_TYPE_COLORS.get(commit_type)
        if color:
            prefix = match.group(0)
            lines[0] = _colorize(prefix, Colors.BOLD, color) + lines[0][len(prefix):]
    return '\n'.join(lines)


class Spinner:
    """Animated spinner for long operations. Use as context manager."""
    FRAMES_UNICODE = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    FRAMES_ASCII = ['-', '\\', '|', '/']

    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()
        self._frames = self.FRAMES_UNICODE if UNICODE_ENABLED else self.FRAMES_ASCII

    def _spin(self):
        idx = 0
        while not self._stop_event.is_set():
            frame = self._frames[idx % len(self._frames)]
            print(f'\r\033[K{frame} ', end='', flush=True)
            idx += 1
            self._stop_event.wait(0.08)

    def __enter__(self):
        if sys.stdout.isatty():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *args):
        self._stop_event.set()
        if self._thread:
            self._thread.join()
        if sys.stdout.isatty():
            print('\r\033[K', end='', flush=True)


__all__ = [
    "Colors", "COLORS_ENABLED", "UNICODE_ENABLED",
    "CHECK", "CROSS", "ARROW", "BULLET",
    "success", "error", "warning", "info", "dim", "bold", "highlight",
    "print_success", "print_error", "print_warning", "print_box",
    "colorize_commit_type", "Spinner", "COMMIT_TYPE_COLORS",
]
