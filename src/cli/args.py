"""CLI Argument Parsing"""

import argparse
import argcomplete

from src import COMMIT_TYPE_NAMES, __version__


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='cm',
        description='Generate AI-powered commit messages',
        epilog='Example: cm (copies message to clipboard)'
    )

    parser.add_argument('-v', '--version', action='version', version=f'%(prog)s {__version__}')

    # Generation options
    parser.add_argument('-c', '--choose', type=int, nargs='?', const=2, default=None, metavar='N', help='Show N options (default: 2), pick one')
    parser.add_argument('--hint', type=str, metavar='TEXT', help='Add context: --hint "fixing the login bug"')
    parser.add_argument('-t', '--type', type=str, choices=COMMIT_TYPE_NAMES, help='Force commit type')
    parser.add_argument('-j', '--jira', type=str, metavar='TICKET', help='Add JIRA ticket: -j PROJ-123')
    parser.add_argument('--ticket-prefix', type=str, metavar='PREFIX', help='Ticket reference prefix (default: Refs)')

    # Style options
    parser.add_argument('-s', '--style', type=str, choices=['conventional', 'simple', 'detailed'], help='Commit message style')
    parser.add_argument('--no-body', action='store_true', help='Generate subject line only, no bullet points')

    # LLM options
    parser.add_argument('-p', '--provider', type=str, choices=['auto', 'ollama', 'claude'], help='LLM provider')
    parser.add_argument('-m', '--model', type=str, metavar='MODEL', help='Model name')
    parser.add_argument('--warmup', action='store_true', help='Pre-load Ollama model into memory')

    # Output options
    parser.add_argument('--no-copy', action='store_true', help='Print message only, do not copy to clipboard')
    parser.add_argument('--verbose', action='store_true', help='Show debug info (prompt size, tokens used)')

    # Setup/config
    parser.add_argument('--setup', action='store_true', help='Configure defaults')
    parser.add_argument('--display-config', action='store_true', help='Show current configuration')
    parser.add_argument('--install-completion', action='store_true', help='Install shell tab completion')

    argcomplete.autocomplete(parser)
    return parser.parse_args()
