"""CLI Main Entry Point"""

import os
import re
import time

from src import COMMIT_TYPE_NAMES
from src.config import load_config
from src.git import GitAnalyzer, GitError, DiffProcessor
from src.llm import get_client, LLMError, OllamaClient
from src.prompts import PromptBuilder, PromptConfig
from src.output import success, info, dim, bold, print_error, print_box, CHECK

from src.cli.args import parse_args
from src.cli.commands import display_config, run_setup, run_install_completion, run_warmup
from src.cli.utils import clean_commit_message, copy_to_clipboard, display_options, TYPES_PATTERN


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
        ticket = args.jira.upper()
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
