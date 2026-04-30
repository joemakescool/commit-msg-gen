"""CLI Commands"""

import os
import sys
import time

from src.config import Config, load_config, save_config, get_config_path
from src.llm import get_client, OllamaClient
from src.output import bold, dim, info, print_success, print_error


def _format_api_key_status(config) -> str:
    """Render api_key status without exposing the secret."""
    if config.api_key:
        suffix = config.api_key[-4:] if len(config.api_key) >= 4 else "****"
        return f"configured (...{suffix}, ~/.cmrc)"
    if os.environ.get('ANTHROPIC_API_KEY'):
        return "configured (ANTHROPIC_API_KEY env var)"
    return "not set"


def display_config() -> int:
    """Display current configuration."""
    config = load_config()
    config_path = get_config_path()

    print(f"\n{bold('Current Configuration')}\n")

    if config_path:
        print(f"  {dim('Loaded from:')} {config_path}")
    else:
        print(f"  {dim('Loaded from:')} defaults (no .cmrc found)")

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
    print(f"    api_key:           {info(_format_api_key_status(config))}")
    print(f"    style:             {info(config.style)}")
    print(f"    include_body:      {info(str(config.include_body).lower())}")
    print(f"    max_subject_length: {info(str(config.max_subject_length))}")
    print(f"    ticket_prefix:     {info(config.ticket_prefix)}")

    print(f"\n  {dim('Config locations:')}")
    print(f"    Local:  .cmrc (in current directory)")
    print(f"    Global: ~/.cmrc")
    print(f"\n  {dim('Run')} cm --setup {dim('to configure')}\n")

    return 0


def run_setup() -> int:
    """Quick setup wizard."""
    display_config()
    print(f"{bold('Setup Wizard')}\n")

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
    api_key = None
    if provider == 'ollama':
        print(f"\nRecommended models (7B+ for best results):")
        print(f"  - mistral:7b      (fast, good quality)")
        print(f"  - llama3.1:8b     (best overall)")
        print(f"  - gemma2:9b       (detailed, slower)")
        print(f"\nNote: 3B models often hallucinate. Use 7B+ for reliable results.\n")
        model = input("Model (Enter for mistral:7b): ").strip() or "mistral:7b"
    elif provider == 'claude':
        print(f"\n{bold('API key')}")
        print(dim("  Get one at https://console.anthropic.com/"))
        env_key = os.environ.get('ANTHROPIC_API_KEY')
        if env_key:
            print(f"  {dim('ANTHROPIC_API_KEY is already set in your environment.')}")
            entered = input("Paste a key to override, or press Enter to keep using the env var: ").strip()
            api_key = entered or None
        else:
            entered = input("Paste your API key (starts with sk-ant-): ").strip()
            api_key = entered or None
            if not api_key:
                print(dim("  No key provided. Set ANTHROPIC_API_KEY in your shell before running cm."))

        print(f"\n{bold('Claude model')}")
        print(f"  1. claude-opus-4-7      (sharpest, best for multi-file commits)")
        print(f"  2. claude-sonnet-4-6    (balanced speed and quality)")
        print(f"  3. claude-haiku-4-5     (fastest, cheapest)\n")
        claude_models = {
            '1': 'claude-opus-4-7',
            '2': 'claude-sonnet-4-6',
            '3': 'claude-haiku-4-5',
        }
        while True:
            choice = input("Select [1/2/3] (Enter for opus): ").strip()
            if choice == '':
                model = 'claude-opus-4-7'
                break
            if choice in claude_models:
                model = claude_models[choice]
                break

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

    print("\nInclude bullet points in commit body? [Y/n]: ", end='')
    include_body = input().strip().lower() != 'n'

    print("\nMax subject line length (Enter for 72): ", end='')
    max_len_input = input().strip()
    max_subject_length = int(max_len_input) if max_len_input.isdigit() else 72

    print(f"\nTicket reference prefix (Enter for Refs): ", end='')
    print(dim("  e.g., Refs, Closes, Fixes"))
    ticket_prefix = input().strip() or "Refs"

    config = Config(
        provider=provider,
        model=model,
        api_key=api_key,
        style=style,
        include_body=include_body,
        max_subject_length=max_subject_length,
        ticket_prefix=ticket_prefix,
    )
    path = save_config(config, global_config=True)

    print_success(f"Saved to {path}")
    return 0


def run_install_completion() -> int:
    """Install shell tab completion."""
    shell = os.environ.get('SHELL', '')

    print(f"\n{bold('Tab Completion Setup')}\n")

    if 'zsh' in shell:
        rc_file = os.path.expanduser('~/.zshrc')
        line = 'eval "$(register-python-argcomplete cm)"'
        print(f"Add this line to {dim(rc_file)}:\n")
        print(f"  {line}\n")
        print(f"Then run: {dim('source ~/.zshrc')}")
    elif 'bash' in shell:
        rc_file = os.path.expanduser('~/.bashrc')
        line = 'eval "$(register-python-argcomplete cm)"'
        print(f"Add this line to {dim(rc_file)}:\n")
        print(f"  {line}\n")
        print(f"Then run: {dim('source ~/.bashrc')}")
    elif sys.platform == 'win32':
        print("For PowerShell, run:\n")
        print("  register-python-argcomplete --shell powershell cm | Out-String | Invoke-Expression\n")
        print("To make it permanent, add to your $PROFILE:\n")
        print("  register-python-argcomplete --shell powershell cm | Out-String | Invoke-Expression")
    else:
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
