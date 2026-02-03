"""
Output Module

Handles colored terminal output.
Falls back gracefully if colors aren't supported.

Why not use 'rich' or 'colorama'?
- Zero dependencies
- Simple needs (just a few colors)
- Works on most modern terminals including Windows 10+
"""

import sys
import os


# ANSI color codes
class Colors:
    """ANSI escape codes for terminal colors."""
    
    # Styles
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # Colors
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    GRAY = '\033[90m'


def _supports_color() -> bool:
    """
    Check if the terminal supports color output.
    """
    # Disable colors if explicitly requested
    if os.environ.get('NO_COLOR'):
        return False
    
    # Force colors if explicitly requested
    if os.environ.get('FORCE_COLOR'):
        return True
    
    # Check if stdout is a terminal
    if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
        return False
    
    # Windows 10+ supports ANSI codes in newer terminals
    if sys.platform == 'win32':
        # Enable ANSI codes on Windows
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # Enable virtual terminal processing
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    
    # Unix-like systems generally support colors
    return True


# Check once at module load
COLORS_ENABLED = _supports_color()


def _colorize(text: str, *codes: str) -> str:
    """Apply color codes to text if colors are enabled."""
    if not COLORS_ENABLED:
        return text
    return f"{''.join(codes)}{text}{Colors.RESET}"


# Convenience functions
def success(text: str) -> str:
    """Green text for success messages."""
    return _colorize(text, Colors.GREEN)


def error(text: str) -> str:
    """Red text for error messages."""
    return _colorize(text, Colors.RED)


def warning(text: str) -> str:
    """Yellow text for warnings."""
    return _colorize(text, Colors.YELLOW)


def info(text: str) -> str:
    """Cyan text for info."""
    return _colorize(text, Colors.CYAN)


def dim(text: str) -> str:
    """Dimmed text for secondary info."""
    return _colorize(text, Colors.DIM)


def bold(text: str) -> str:
    """Bold text for emphasis."""
    return _colorize(text, Colors.BOLD)


def highlight(text: str) -> str:
    """Magenta text for highlighting."""
    return _colorize(text, Colors.MAGENTA)


# Symbols (with fallbacks for terminals that don't support Unicode)
def _supports_unicode() -> bool:
    """Check if terminal supports Unicode."""
    if sys.platform == 'win32':
        # Check if Windows terminal supports Unicode
        try:
            '✓'.encode(sys.stdout.encoding or 'utf-8')
            return True
        except (UnicodeEncodeError, LookupError):
            return False
    return True


UNICODE_ENABLED = _supports_unicode()

# Symbols with ASCII fallbacks
CHECK = '✓' if UNICODE_ENABLED else '[OK]'
CROSS = '✗' if UNICODE_ENABLED else '[X]'
ARROW = '→' if UNICODE_ENABLED else '->'
BULLET = '•' if UNICODE_ENABLED else '*'
SPINNER = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'] if UNICODE_ENABLED else ['-', '\\', '|', '/']


def success_icon() -> str:
    """Green checkmark."""
    return success(CHECK)


def error_icon() -> str:
    """Red X."""
    return error(CROSS)


def print_success(message: str) -> None:
    """Print a success message with green checkmark."""
    print(f"{success_icon()} {message}")


def print_error(message: str) -> None:
    """Print an error message with red X."""
    print(f"{error_icon()} {error(message)}", file=sys.stderr)


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"{warning('⚠')} {warning(message)}" if UNICODE_ENABLED else f"[!] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"{info(message)}")


def print_box(text: str, max_width: int = 66) -> None:
    """
    Print text inside a bordered box.

    Args:
        text: The text to display (can be multiline)
        max_width: Maximum width of the box content
    """
    lines = text.split('\n')
    content_width = min(max(len(line) for line in lines), max_width)

    # Box characters (with ASCII fallback)
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


# CLI test
if __name__ == "__main__":
    print("Output Module Test")
    print("=" * 40)
    print()
    
    print(f"Colors enabled: {COLORS_ENABLED}")
    print(f"Unicode enabled: {UNICODE_ENABLED}")
    print()
    
    print_success("This is a success message")
    print_error("This is an error message")
    print_warning("This is a warning")
    print_info("This is info")
    print()
    
    print(f"Regular, {bold('bold')}, {dim('dim')}")
    print(f"{success('green')}, {error('red')}, {warning('yellow')}, {info('cyan')}")
    print()
    
    print(f"Symbols: {CHECK} {CROSS} {ARROW} {BULLET}")
