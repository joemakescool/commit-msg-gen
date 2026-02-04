# cm

![cm - AI-powered commit message generator](banner.svg)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![GitHub](https://img.shields.io/badge/github-joemakescool/commit--msg--gen-black.svg)](https://github.com/joemakescool/commit-msg-gen)

**AI-powered git commit messages.** Stage your changes, run `cm`, paste the result.

```
$ git add .
$ cm
Analyzing 3 files... using Claude... done!

┌────────────────────────────────────────────────────────────┐
│ feat(auth): add JWT refresh token rotation                 │
│                                                            │
│ - Implement automatic token refresh before expiry          │
│ - Add refresh token storage in httpOnly cookies            │
│ - Include token family tracking for reuse detection        │
└────────────────────────────────────────────────────────────┘

✓ Copied to clipboard!

$ git commit -m "<paste>"
```

## Why cm?

- **Understands context** — Analyzes your actual diff, not just file names
- **Conventional commits** — Proper `type(scope): subject` format out of the box
- **Works offline** — Use Ollama for free, local generation
- **Zero friction** — Copies to clipboard automatically

## Quick Start

```bash
# Install
pip install git+https://github.com/joemakescool/commit-msg-gen.git

# Use
git add .
cm
git commit   # paste the message
```

That's it. Works immediately with [Ollama](https://ollama.ai) if you have it running, or configure Claude API with `cm --setup`.

## Installation

```bash
pip install git+https://github.com/joemakescool/commit-msg-gen.git
```

<details>
<summary><strong>Windows PATH issues?</strong></summary>

If `cm` isn't recognized after install, add Python Scripts to your PATH:

**Step 1:** Find your Python Scripts path:
```powershell
python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
```

**Step 2:** Add to PATH (pick one):

*GUI method:*
1. Press `Win + R`, type `sysdm.cpl`, press Enter
2. Advanced → Environment Variables
3. Edit `Path` under User variables → Add the scripts path
4. Restart terminal

*PowerShell method:*
```powershell
$scriptsPath = python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
if (!(Test-Path $PROFILE)) { New-Item $PROFILE -Force }
Add-Content $PROFILE "`n`$env:PATH += `";$scriptsPath`""
. $PROFILE
```

**Step 3:** Verify: `cm --version`

</details>

## Usage

### Basic

```bash
cm                          # Generate and copy to clipboard
cm --no-copy                # Print only
cm --verbose                # Show token usage and timing
```

### Guide the AI

```bash
cm --hint "fixing the auth bug"   # Add context
cm -t fix                          # Force commit type
cm -j PROJ-123                     # Append JIRA ticket
cm -c                              # Generate 2 options, pick one
```

### Style Options

```bash
cm -s conventional          # feat(scope): subject + bullets (default)
cm -s simple                # Plain subject + bullets
cm -s detailed              # More comprehensive bullets
cm --no-body                # Subject line only
```

### Provider Selection

```bash
cm -p ollama                # Use local Ollama
cm -p claude                # Use Claude API
cm -m mistral:7b            # Specify model
```

### All Commands

| Command | Description |
|---------|-------------|
| `cm` | Generate message, copy to clipboard |
| `cm -c` | Choose from 2 options |
| `cm --hint TEXT` | Add context for better messages |
| `cm -t TYPE` | Force commit type (feat, fix, etc.) |
| `cm -j TICKET` | Append JIRA reference |
| `cm -s STYLE` | Set style: conventional, simple, detailed |
| `cm --no-body` | Subject line only |
| `cm -p PROVIDER` | Use: auto, ollama, claude |
| `cm -m MODEL` | Specify model name |
| `cm --warmup` | Pre-load Ollama model |
| `cm --no-copy` | Don't copy to clipboard |
| `cm --verbose` | Show debug info |
| `cm --setup` | Configure defaults |
| `cm --display-config` | Show current config |
| `cm --install-completion` | Shell tab completion |
| `cm -v` | Show version |

## Configuration

Run `cm --setup` to configure defaults, or create a `.cmrc` file manually.

**Config file locations (checked in order):**
1. `.cmrc` in current directory (project-specific)
2. `.cmrc` in home directory (global default)

**Example `.cmrc`:**
```json
{
  "provider": "ollama",
  "model": "gemma3:4b",
  "style": "conventional",
  "include_body": true,
  "max_subject_length": 50
}
```

| Setting | Options | Description |
|---------|---------|-------------|
| `provider` | `auto`, `ollama`, `claude` | AI provider to use |
| `model` | any model name | Model override (e.g., `llama3.2:3b`) |
| `style` | `conventional`, `simple`, `detailed` | Commit message format |
| `include_body` | `true`, `false` | Include bullet points in body |
| `max_subject_length` | number | Max chars for subject line (default: 50) |

### Styles

| Style | Format | Example |
|-------|--------|---------|
| `conventional` | `type(scope): subject` + bullets | `feat(api): add rate limiting` |
| `simple` | Plain subject + bullets | `Add rate limiting to API` |
| `detailed` | `type(scope): subject` + more bullets | Longer descriptions, more context |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CM_PROVIDER` | Override provider: `ollama` or `claude` |
| `CM_MODEL` | Override model name |
| `CM_TIMEOUT` | Request timeout in seconds (default: 300). Increase for slow CPU inference. |
| `ANTHROPIC_API_KEY` | Claude API key |
| `OLLAMA_HOST` | Ollama server URL (default: `http://localhost:11434`) |

## Commit Types

| Type | When to use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code restructuring |
| `chore` | Maintenance, deps |
| `docs` | Documentation |
| `test` | Tests |
| `style` | Formatting |
| `perf` | Performance improvement |
| `ci` | CI/CD changes |
| `build` | Build system changes |

Use `!` for breaking changes: `feat!(api): remove deprecated endpoint`

## AI Providers

### Ollama (Free, Local)

[Install Ollama](https://ollama.ai), then:

```bash
ollama pull mistral:7b    # Recommended - fast and reliable
ollama serve              # Start the server
```

**Recommended models (7B+ for best results):**
- `mistral:7b` - Fast, good quality (recommended)
- `llama3.1:8b` - Best overall
- `gemma2:9b` - Most detailed, slower

**Note:** 3B models often hallucinate and ignore the diff. Use 7B+ for reliable results.

**Pro tip:** Pre-load the model for faster first response:
```bash
cm --warmup
```

### Claude API

Get an API key from [Anthropic](https://console.anthropic.com), then:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # Linux/macOS
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # PowerShell
```

<details>
<summary><strong>Troubleshooting</strong></summary>

| Problem | Solution |
|---------|----------|
| `cm` not recognized | Re-run `pip install .` or restart terminal |
| "Ollama not running" | Run `ollama serve` in another terminal |
| "Model not found" | Run `ollama pull <model-name>` |
| "No staged changes" | Run `git add .` first |
| Clipboard not working | Use `cm --no-copy` and copy manually |
| Hallucinated messages | Use 7B+ model: `cm -m mistral:7b` (3B models often ignore the diff) |
| Slow response | Try `mistral:7b` (faster than larger models) |
| Timeout on CPU | Increase timeout: `set CM_TIMEOUT=600` or pre-load: `cm --warmup` |

</details>

<details>
<summary><strong>Project Structure</strong></summary>

```
src/
├── cli/                 # Command-line interface
│   ├── args.py          # Argument parsing
│   ├── commands.py      # Setup, config, warmup
│   ├── main.py          # Entry point
│   └── utils.py         # Clipboard, formatting
├── config/              # Configuration management
├── git/                 # Git operations
│   ├── analyzer.py      # Extract staged changes
│   └── diff_processor.py # Filter and prioritize diffs
├── llm/                 # LLM providers
│   ├── base.py          # Abstract client, system prompt
│   ├── claude.py        # Anthropic API
│   └── ollama.py        # Local Ollama
├── output/              # Terminal colors and formatting
└── prompts/             # Prompt construction
    └── builder.py       # Build context for LLM
```

</details>

## License

MIT
