# CLAUDE.md

This file provides context for Claude Code sessions working on this project.

## Project Overview

**commit-msg-gen** (`cm`) is a CLI tool that generates AI-powered git commit messages. It analyzes staged changes, sends them to an LLM (Ollama or Claude), and copies the generated message to the clipboard.

## Quick Commands

```bash
# Run the CLI
cm                      # Generate commit message
cm --display-config     # Show current config
cm --setup              # Interactive setup wizard
python -m src.cli       # Alternative way to run

# Install in dev mode
python -m pip install -e .

# Test imports
python -c "from src.cli import main; print('OK')"
```

## Project Structure

```
src/
├── __init__.py          # Package root (version, COMMIT_TYPES, COMMIT_TYPE_NAMES)
├── cli/                 # Command-line interface
│   ├── __init__.py      # Exports main()
│   ├── __main__.py      # Entry for python -m src.cli
│   ├── args.py          # Argument parsing (argparse + argcomplete)
│   ├── commands.py      # Subcommands: setup, display_config, warmup, install_completion
│   ├── main.py          # Main entry point, orchestrates the flow
│   └── utils.py         # Helpers: copy_to_clipboard, clean_commit_message, display_options
├── config/              # Configuration management
│   └── __init__.py      # Config dataclass, load_config(), save_config(), ConfigManager
├── git/                 # Git operations
│   ├── __init__.py      # Exports all git classes
│   ├── analyzer.py      # GitAnalyzer: extracts staged changes via git commands
│   └── diff_processor.py # DiffProcessor: filters noise, prioritizes files, builds LLM context
├── llm/                 # LLM client abstraction
│   ├── __init__.py      # Exports get_client(), PROVIDERS registry
│   ├── base.py          # LLMClient ABC, LLMResponse, LLMError, SYSTEM_PROMPT
│   ├── claude.py        # ClaudeClient: Anthropic API
│   └── ollama.py        # OllamaClient: local Ollama server
├── output/              # Terminal formatting
│   └── __init__.py      # Colors, symbols, print_success/error/box helpers
└── prompts/             # Prompt construction
    ├── __init__.py      # Exports PromptBuilder, PromptConfig
    └── builder.py       # Builds structured prompts for commit message generation
```

## Key Patterns

### Package Imports
All packages expose their API through `__init__.py`:
```python
from src.cli import main
from src.git import GitAnalyzer, DiffProcessor
from src.llm import get_client, LLMError, OllamaClient
from src.config import load_config, save_config, Config
from src.output import print_success, print_error, bold, dim
from src.prompts import PromptBuilder, PromptConfig
```

### LLM Provider Registry
Adding a new provider:
1. Create `src/llm/newprovider.py` with class extending `LLMClient`
2. Import in `src/llm/__init__.py`
3. Add to `PROVIDERS` dict

### Configuration
- Config file: `.cmrc` (JSON)
- Locations checked: `./cmrc` (local) → `~/.cmrc` (global) → defaults
- CLI args override env vars override config file

### Entry Point
Defined in `pyproject.toml`:
```toml
[project.scripts]
cm = "src.cli:main"
```

## Important Constants

In `src/__init__.py`:
- `__version__` - Package version
- `COMMIT_TYPES` - Dict of type → description
- `COMMIT_TYPE_NAMES` - List of valid commit types (feat, fix, refactor, etc.)

## Flow

1. `cm` command → `src/cli/main.py:main()`
2. Parse args → Check for subcommands (setup, display-config, warmup)
3. `GitAnalyzer.get_staged_changes()` → Get staged diff
4. `DiffProcessor.process()` → Filter noise, prioritize files
5. `PromptBuilder.build()` → Construct LLM prompt
6. `get_client()` → Get appropriate LLM client
7. `client.generate()` → Call LLM API
8. `copy_to_clipboard()` → Copy result
9. `print_box()` → Display to user

## Testing

```bash
# Stage some changes first
git add .

# Test the full flow
cm --verbose

# Test specific components
python -c "from src.git import GitAnalyzer; print(GitAnalyzer().get_staged_changes())"
```

## Common Issues

1. **`cm` not recognized**: Reinstall with `pip install -e .` or add Python Scripts to PATH
2. **PowerShell alias conflict**: Remove any `function cm` from `$PROFILE`
3. **Import errors after restructure**: Clear `__pycache__` directories

## Dependencies

- `anthropic` - Claude API SDK
- `argcomplete` - Shell tab completion

No other external dependencies - uses stdlib for git (subprocess), Ollama (urllib), colors (ANSI codes).
