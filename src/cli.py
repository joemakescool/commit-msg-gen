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
import time

import argcomplete

from src import COMMIT_TYPE_NAMES, __version__

# Regex pattern for commit types
TYPES_PATTERN = '|'.join(COMMIT_TYPE_NAMES)
from src.git_analyzer import GitAnalyzer, GitError
from src.diff_processor import DiffProcessor
from src.prompt_builder import PromptBuilder, PromptConfig
from src.llm_client import get_client, LLMError, OllamaClient
from src.config import load_config, save_config, get_config_path, Config
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

    parser.add_argument('-v', '--version', action='version', version=f'%(prog)s {__version__}')

    # Generation options
    parser.add_argument('-c', '--choose', action='store_true', help='Show 2 options, pick one')
    parser.add_argument('--hint', type=str, metavar='TEXT', help='Add context: --hint "fixing the login bug"')
    parser.add_argument('-t', '--type', type=str, choices=COMMIT_TYPE_NAMES, help='Force commit type')
    parser.add_argument('-j', '--jira', type=str, metavar='TICKET', help='Add JIRA ticket: -j PROJ-123')

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


def display_config() -> int:
    """Display current configuration."""
    config = load_config()
    config_path = get_config_path()

    print(f"\n{bold('Current Configuration')}\n")

    # Show source
    if config_path:
        print(f"  {dim('Loaded from:')} {config_path}")
    else:
        print(f"  {dim('Loaded from:')} defaults (no .cmrc found)")

    # Show env var overrides if set
    env_provider = os.environ.get('CM_PROVIDER')
    env_model = os.environ.get('CM_MODEL')
    if env_provider or env_model:
        print(f"  {dim('Environment overrides:')}")
        if env_provider:
            print(f"    CM_PROVIDER={env_provider}")
        if env_model:
            print(f"    CM_MODEL={env_model}")

    print()
    print(f"  {bold('Settings:')}")
    print(f"    provider:          {info(config.provider)}")
    print(f"    model:             {info(config.model or 'auto')}")
    print(f"    style:             {info(config.style)}")
    print(f"    include_body:      {info(str(config.include_body).lower())}")
    print(f"    max_subject_length: {info(str(config.max_subject_length))}")

    print(f"\n  {dim('Config locations:')}")
    print(f"    Local:  .cmrc (in current directory)")
    print(f"    Global: ~/.cmrc")
    print(f"\n  {dim('Run')} cm --setup {dim('to configure')}\n")

    return 0


def run_setup() -> int:
    """Quick setup wizard."""
    # Show current config first
    display_config()

    print(f"{bold('Setup Wizard')}\n")

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


def run_install_completion() -> int:
    """Install shell tab completion."""
    shell = os.environ.get('SHELL', '')

    print(f"\n{bold('Tab Completion Setup')}\n")

    if 'zsh' in shell:
        # Zsh
        rc_file = os.path.expanduser('~/.zshrc')
        line = 'eval "$(register-python-argcomplete cm)"'
        print(f"Add this line to {dim(rc_file)}:\n")
        print(f"  {line}\n")
        print(f"Then run: {dim('source ~/.zshrc')}")

    elif 'bash' in shell:
        # Bash
        rc_file = os.path.expanduser('~/.bashrc')
        line = 'eval "$(register-python-argcomplete cm)"'
        print(f"Add this line to {dim(rc_file)}:\n")
        print(f"  {line}\n")
        print(f"Then run: {dim('source ~/.bashrc')}")

    elif sys.platform == 'win32':
        # PowerShell
        print("For PowerShell, run:\n")
        print("  register-python-argcomplete --shell powershell cm | Out-String | Invoke-Expression\n")
        print("To make it permanent, add to your $PROFILE:\n")
        print("  register-python-argcomplete --shell powershell cm | Out-String | Invoke-Expression")

    else:
        # Generic instructions
        print("Run one of these based on your shell:\n")
        print(f"  {dim('# Bash/Zsh')}")
        print('  eval "$(register-python-argcomplete cm)"\n')
        print(f"  {dim('# PowerShell')}")
        print("  register-python-argcomplete --shell powershell cm | Out-String | Invoke-Expression\n")
        print(f"  {dim('# Fish')}")
        print("  register-python-argcomplete --shell fish cm | source")

    print(f"\n{dim('After setup, press TAB to autocomplete flags.')}")
    return 0


def run_warmup(provider: str | None, model: str | None) -> int:
    """Pre-load Ollama model into memory."""

    # Force Ollama for warmup
    if provider and provider != 'ollama':
        print_error("--warmup only works with Ollama (local models)")
        return 1

    try:
        client = get_client(provider='ollama', model=model)
    except Exception as e:
        print_error(f"Failed to connect to Ollama: {e}")
        return 1

    if not isinstance(client, OllamaClient):
        print_error("--warmup only works with Ollama")
        return 1

    if client._is_model_loaded():
        print_success(f"Model {bold(client.model)} is already loaded")
        return 0

    print(f"Loading {bold(client.model)}... ", end='', flush=True)
    start = time.time()
    client.warmup()
    elapsed = time.time() - start

    if client._is_model_loaded():
        print_success(f"ready! ({elapsed:.1f}s)")
        print(dim(f"Model will stay loaded for ~10 minutes"))
        return 0
    else:
        print_error("failed to load model")
        return 1


def main() -> int:
    args = parse_args()

    if args.install_completion:
        return run_install_completion()

    if args.display_config:
        return display_config()

    if args.setup:
        return run_setup()

    # Load config for provider/model defaults
    config = load_config()
    provider = args.provider or os.environ.get('CM_PROVIDER') or config.provider
    model = args.model or os.environ.get('CM_MODEL') or config.model

    if args.warmup:
        return run_warmup(provider, model)

    # Override config with CLI args
    if args.style:
        config.style = args.style
    if args.no_body:
        config.include_body = False
    
    # Timing for verbose mode
    timings = {}

    # Get staged changes
    t0 = time.time()
    try:
        analyzer = GitAnalyzer()
        changes = analyzer.get_staged_changes()
    except GitError as e:
        print_error(str(e))
        return 1
    timings['git'] = time.time() - t0

    if changes.is_empty:
        print_error("No staged changes. Run 'git add' first.")
        return 1

    # Process diff
    t0 = time.time()
    processor = DiffProcessor()
    processed = processor.process(changes)
    timings['diff'] = time.time() - t0

    # Show analysis message
    print(f"Analyzing {bold(str(processed.total_files))} files... ", end='', flush=True)

    # Build prompt with config settings
    t0 = time.time()
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
    timings['prompt'] = time.time() - t0

    # Call LLM
    try:
        t0 = time.time()
        client = get_client(provider=provider, model=model)
        print(f"using {info(client.name)}... ", end='', flush=True)

        # For Ollama: check if model needs loading, show message and warmup
        if isinstance(client, OllamaClient) and not client._is_model_loaded():
            print(dim("loading model... "), end='', flush=True)
            t_warmup = time.time()
            client.warmup()
            timings['warmup'] = time.time() - t_warmup

        t_gen = time.time()
        response = client.generate(prompt)
        timings['generate'] = time.time() - t_gen
        timings['llm_total'] = time.time() - t0
    except LLMError as e:
        print()
        print_error(str(e))
        return 1

    # Verbose output
    if args.verbose:
        print()
        print(dim(f"  Prompt: ~{len(prompt)//4} tokens ({len(prompt)} chars)"))
        print(dim(f"  Response: {response.tokens_used} tokens"))
        if response.tokens_used > 0 and timings.get('generate'):
            tok_per_sec = response.tokens_used / timings['generate']
            print(dim(f"  Speed: {tok_per_sec:.1f} tokens/sec"))
        print(dim(f"  Timings: git={timings['git']:.2f}s, diff={timings['diff']:.2f}s, prompt={timings['prompt']:.2f}s, generate={timings.get('generate', 0):.2f}s"))
    
    # Handle response
    if args.choose:
        parts = re.split(r'\[Option \d+\]\s*', response.content)
        options = [p.strip() for p in parts if p.strip()]

        if len(options) <= 1:
            type_pattern = rf'\n(?=\[?(?:{TYPES_PATTERN})[\(!:])'
            parts = re.split(type_pattern, response.content.strip())
            options = [p.strip() for p in parts if p.strip()]

        cleaned_options = []
        for opt in options:
            opt = clean_commit_message(opt)
            opt = re.sub(rf'^\[?({TYPES_PATTERN})\(', r'\1(', opt)
            lines = opt.split('\n')
            if lines[0].endswith(']'):
                lines[0] = lines[0][:-1]
            cleaned_options.append('\n'.join(lines))
        options = cleaned_options

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
