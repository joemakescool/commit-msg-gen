"""
Commit Message Generator - CLI

Usage: cm [options]
Generates commit messages from staged changes and copies to clipboard.
"""

import argparse
import subprocess
import sys

from git_analyzer import GitAnalyzer, GitError
from diff_processor import DiffProcessor
from prompt_builder import PromptBuilder, PromptConfig
from llm_client import get_client, LLMError
from config import load_config, save_config, Config
from output import (
    success, info, dim, bold,
    print_success, print_error,
    CHECK
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='cm',
        description='Generate AI-powered commit messages',
        epilog='Example: cm → copies message to clipboard'
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
        choices=['feat', 'fix', 'refactor', 'chore', 'docs', 'test', 'style'],
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
        '--no-copy',
        action='store_true',
        help='Print message only, do not copy to clipboard'
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
    except Exception:
        return False


def run_setup() -> int:
    """Quick setup wizard."""
    print(f"\n{bold('Commit Message Generator Setup')}\n")
    
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
    
    config = Config(provider=provider, model=model)
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
    
    # Load config
    config = load_config()
    provider = args.provider or config.provider
    model = args.model or config.model
    
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
    
    print(f"Analyzing {bold(str(processed.total_files))} files... ", end='', flush=True)
    
    # Build prompt
    prompt_config = PromptConfig(
        hint=args.hint,
        forced_type=args.type,
        num_options=2 if args.choose else 1,
        file_count=processed.total_files
    )
    prompt = PromptBuilder().build(processed, prompt_config)
    
    # Call LLM
    try:
        client = get_client(provider=provider, model=model)
        print(f"using {info(client.name)}... ", end='', flush=True)
        response = client.generate(prompt)
    except LLMError as e:
        print()
        print_error(str(e))
        return 1
    
    # Handle response
    if args.choose:
        import re
        
        # Try to split by [Option N] markers first
        parts = re.split(r'\[Option \d+\]\s*', response.content)
        options = [p.strip() for p in parts if p.strip()]
        
        # If that didn't work, try splitting by commit type patterns
        if len(options) <= 1:
            # Split on lines that start with commit types
            type_pattern = r'\n(?=\[?(?:feat|fix|refactor|chore|docs|test|style)\()'
            parts = re.split(type_pattern, response.content.strip())
            options = [p.strip() for p in parts if p.strip()]
        
        # Clean up each option - remove wrapping brackets if present
        cleaned_options = []
        for opt in options:
            # Remove leading [ if the message starts with [type(
            opt = re.sub(r'^\[?(feat|fix|refactor|chore|docs|test|style)\(', r'\1(', opt)
            # Remove trailing ] if present at end of first line
            lines = opt.split('\n')
            if lines[0].endswith(']'):
                lines[0] = lines[0][:-1]
            cleaned_options.append('\n'.join(lines))
        options = cleaned_options
        
        # Still just one? Use it as-is
        if not options:
            options = [response.content.strip()]
        
        idx = display_options(options)
        if idx is None:
            print(dim("Cancelled."))
            return 2
        message = options[idx]
    else:
        message = response.content.strip()
        print(success("done!"))
    
    # Append JIRA ticket if provided
    if args.jira:
        ticket = args.jira.upper()  # PROJ-123 format
        message = f"{message}\n\nRefs: {ticket}"
    
    # Output
    print()
    
    # Clean box around message
    lines = message.split('\n')
    max_len = max(len(line) for line in lines)
    box_width = min(max_len, 66)
    
    print(dim('┌─' + '─' * box_width + '─┐'))
    for line in lines:
        padding = ' ' * (box_width - len(line))
        print(dim('│ ') + line + padding + dim(' │'))
    print(dim('└─' + '─' * box_width + '─┘'))
    
    # Copy to clipboard
    if not args.no_copy:
        if copy_to_clipboard(message):
            print(f"\n{success(CHECK)} Copied to clipboard!")
            print(f"{dim('Paste with:')} git commit -m \"Ctrl+V\"")
        else:
            print(f"\n{dim('(Could not copy to clipboard)')}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
