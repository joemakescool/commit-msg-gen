"""
Commit Message Generator - CLI

Usage: cm [options]
Generates commit messages from staged changes and copies to clipboard.
"""

import argparse
import os
import re
import subprocess
import sys

from src import COMMIT_TYPE_NAMES, __version__  # Centralized in __init__.py
from src.git_analyzer import GitAnalyzer, GitError
from src.diff_processor import DiffProcessor
from src.prompt_builder import PromptBuilder, PromptConfig
from src.llm_client import get_client, LLMError, OllamaClient
from src.config import load_config, save_config, Config
from src.output import (
    success, info, dim, bold,
    print_success, print_error, print_box,
    CHECK
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='cm',
        description='Generate AI-powered commit messages',
        epilog='Example: cm (copies message to clipboard)'
    )

    parser.add_argument(
        '-v', '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )

    parser.add_argument(
        '-c', '--choose',
        action='store_true',
        help='Show 2 options, pick one'
    )
    
    parser.add_argument(
        '--hint',
        type=str,
        metavar='TEXT',
        help='Add context: --hint "fixing the login bug"'
    )
    
    parser.add_argument(
        '-t', '--type',
        type=str,
        choices=COMMIT_TYPE_NAMES,  # Centralized in __init__.py
        help='Force commit type'
    )
    
    parser.add_argument(
        '-j', '--jira',
        type=str,
        metavar='TICKET',
        help='Add JIRA ticket: -j PROJ-123'
    )
    
    parser.add_argument(
        '-p', '--provider',
        type=str,
        choices=['auto', 'ollama', 'claude'],
        help='LLM provider'
    )
    
    parser.add_argument(
        '-m', '--model',
        type=str,
        metavar='MODEL',
        help='Model name'
    )
    
    parser.add_argument(
        '--setup',
        action='store_true',
        help='Configure defaults'
    )

    parser.add_argument(
        '-s', '--style',
        type=str,
        choices=['conventional', 'simple', 'detailed'],
        help='Commit message style'
    )

    parser.add_argument(
        '--no-body',
        action='store_true',
        help='Generate subject line only, no bullet points'
    )

    parser.add_argument(
        '--no-copy',
        action='store_true',
        help='Print message only, do not copy to clipboard'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show debug info (prompt size, tokens used)'
    )

    return parser.parse_args()


def copy_to_clipboard(text: str) -> bool:
    """Copy text to clipboard. Works on Windows, Mac, Linux."""
    try:
        if sys.platform == 'win32':
            subprocess.run(
                ['clip'],
                input=text.encode('utf-8'),
                check=True
            )
        elif sys.platform == 'darwin':
            subprocess.run(
                ['pbcopy'],
                input=text.encode('utf-8'),
                check=True
            )
        else:
            # Linux - try xclip or xsel
            try:
                subprocess.run(
                    ['xclip', '-selection', 'clipboard'],
                    input=text.encode('utf-8'),
                    check=True
                )
            except FileNotFoundError:
                subprocess.run(
                    ['xsel', '--clipboard', '--input'],
                    input=text.encode('utf-8'),
                    check=True
                )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        # CalledProcessError: clipboard command failed
        # FileNotFoundError: clipboard command not found
        # OSError: other OS-level errors (permissions, etc.)
        return False


def run_setup() -> int:
    """Quick setup wizard."""
    print(f"\n{bold('Commit Message Generator Setup')}\n")

    # Provider selection
    print("Choose provider:\n")
    print("  1. Ollama (free, local)")
    print("  2. Claude API (paid)\n")

    while True:
        choice = input("Select [1/2]: ").strip()
        if choice == '1':
            provider = 'ollama'
            break
        elif choice == '2':
            provider = 'claude'
            break

    model = None
    if provider == 'ollama':
        print(f"\nRecommended: llama3.2:3b, gemma3:4b, mistral:7b\n")
        model = input("Model (Enter for default): ").strip() or None

    # Style selection
    print("\nCommit message style:\n")
    print("  1. conventional - type(scope): subject with bullets (default)")
    print("  2. simple - plain subject with bullets")
    print("  3. detailed - type(scope): subject with more bullets\n")

    style = "conventional"
    while True:
        choice = input("Select [1/2/3] (Enter for default): ").strip()
        if choice == '' or choice == '1':
            style = 'conventional'
            break
        elif choice == '2':
            style = 'simple'
            break
        elif choice == '3':
            style = 'detailed'
            break

    # Include body
    print("\nInclude bullet points in commit body? [Y/n]: ", end='')
    include_body = input().strip().lower() != 'n'

    # Max subject length
    print("\nMax subject line length (Enter for 50): ", end='')
    max_len_input = input().strip()
    max_subject_length = int(max_len_input) if max_len_input.isdigit() else 50

    config = Config(
        provider=provider,
        model=model,
        style=style,
        include_body=include_body,
        max_subject_length=max_subject_length,
    )
    path = save_config(config, global_config=True)

    print_success(f"Saved to {path}")
    return 0


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


def main() -> int:
    args = parse_args()
    
    if args.setup:
        return run_setup()

    # Load config with priority: CLI args > env vars > config file > defaults
    config = load_config()
    provider = args.provider or os.environ.get('CM_PROVIDER') or config.provider
    model = args.model or os.environ.get('CM_MODEL') or config.model

    # Override config with CLI args
    if args.style:
        config.style = args.style
    if args.no_body:
        config.include_body = False
    
    # Get staged changes
    try:
        analyzer = GitAnalyzer()
        changes = analyzer.get_staged_changes()
    except GitError as e:
        print_error(str(e))
        return 1
    
    if changes.is_empty:
        print_error("No staged changes. Run 'git add' first.")
        return 1
    
    # Process diff
    processor = DiffProcessor()
    processed = processor.process(changes)

    # Show analysis message
    print(f"Analyzing {bold(str(processed.total_files))} files... ", end='', flush=True)

    # Build prompt with config settings
    prompt_config = PromptConfig(
        hint=args.hint,
        forced_type=args.type,
        num_options=2 if args.choose else 1,
        file_count=processed.total_files,
        style=config.style,
        include_body=config.include_body,
        max_subject_length=config.max_subject_length,
    )
    prompt = PromptBuilder().build(processed, prompt_config)
    
    # Call LLM
    try:
        client = get_client(provider=provider, model=model)
        print(f"using {info(client.name)}... ", end='', flush=True)

        # For Ollama: check if model needs loading, show message and warmup
        if isinstance(client, OllamaClient) and not client._is_model_loaded():
            print(dim("loading model... "), end='', flush=True)
            client.warmup()

        response = client.generate(prompt)
    except LLMError as e:
        print()
        print_error(str(e))
        return 1

    # Verbose output
    if args.verbose:
        print()
        print(dim(f"  Prompt: ~{len(prompt)//4} tokens ({len(prompt)} chars)"))
        print(dim(f"  Response: {response.tokens_used} tokens"))
    
    # Handle response
    # Build type pattern from centralized list
    types_pattern = '|'.join(COMMIT_TYPE_NAMES)

    def clean_commit_message(text: str) -> str:
        """Clean up LLM response to extract just the commit message."""
        # Remove any preamble before the actual commit message
        # Look for the first line that starts with a commit type
        lines = text.strip().split('\n')
        start_idx = 0
        for i, line in enumerate(lines):
            # Check if line starts with a commit type (with optional backticks)
            if re.match(rf'^[`\s]*({types_pattern})[\(!:]', line):
                start_idx = i
                break

        # Rejoin from the commit message start
        cleaned = '\n'.join(lines[start_idx:])

        # Remove backticks from subject line
        lines = cleaned.split('\n')
        if lines:
            # Remove surrounding backticks from first line
            lines[0] = lines[0].strip('`').strip()

        return '\n'.join(lines)

    if args.choose:
        # Try to split by [Option N] markers first
        parts = re.split(r'\[Option \d+\]\s*', response.content)
        options = [p.strip() for p in parts if p.strip()]

        # If that didn't work, try splitting by commit type patterns
        if len(options) <= 1:
            # Split on lines that start with commit types
            type_pattern = rf'\n(?=\[?(?:{types_pattern})[\(!:])'
            parts = re.split(type_pattern, response.content.strip())
            options = [p.strip() for p in parts if p.strip()]

        # Clean up each option
        cleaned_options = []
        for opt in options:
            opt = clean_commit_message(opt)
            # Remove leading [ if the message starts with [type(
            opt = re.sub(rf'^\[?({types_pattern})\(', r'\1(', opt)
            # Remove trailing ] if present at end of first line
            lines = opt.split('\n')
            if lines[0].endswith(']'):
                lines[0] = lines[0][:-1]
            cleaned_options.append('\n'.join(lines))
        options = cleaned_options

        # Still just one? Use it as-is
        if not options:
            options = [clean_commit_message(response.content.strip())]

        idx = display_options(options)
        if idx is None:
            print(dim("Cancelled."))
            return 2
        message = options[idx]
        print(success("done!"))
    else:
        message = clean_commit_message(response.content.strip())
        print(success("done!"))
    
    # Append JIRA ticket if provided
    if args.jira:
        ticket = args.jira.upper()  # PROJ-123 format
        message = f"{message}\n\nRefs: {ticket}"
    
    # Output
    print()
    print_box(message)
    
    # Copy to clipboard
    if not args.no_copy:
        if copy_to_clipboard(message):
            print(f"\n{success(CHECK)} Copied to clipboard!")
            print(dim("Run: git commit → paste in editor, or:"))
            print(dim("     git commit -m \"<paste>\""))
        else:
            print(f"\n{dim('(Could not copy to clipboard)')}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
