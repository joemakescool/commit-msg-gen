"""Terminal Output Formatting Package"""

import sys
import os


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


def print_box(text: str, max_width: int = 66) -> None:
    lines = text.split('\n')
    content_width = min(max(len(line) for line in lines), max_width)

    if UNICODE_ENABLED:
        top = f'┌─{"─" * content_width}─┐'
        bottom = f'└─{"─" * content_width}─┘'
        side = '│'
    else:
        top = f'+-{"-" * content_width}-+'
        bottom = f'+-{"-" * content_width}-+'
        side = '|'

    print(dim(top))
    for line in lines:
        padding = ' ' * (content_width - len(line))
        print(f"{dim(side)} {line}{padding} {dim(side)}")
    print(dim(bottom))


__all__ = [
    "Colors", "COLORS_ENABLED", "UNICODE_ENABLED",
    "CHECK", "CROSS", "ARROW", "BULLET",
    "success", "error", "warning", "info", "dim", "bold", "highlight",
    "print_success", "print_error", "print_warning", "print_box",
]
