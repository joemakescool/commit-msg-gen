"""CLI Main Entry Point"""

import os
import re
import sys
import time

from src import COMMIT_TYPE_NAMES
from src.config import load_config
from src.git import GitAnalyzer, GitError, DiffProcessor
from src.llm import get_client, LLMError, OllamaClient
from src.prompts import PromptBuilder, PromptConfig
from src.output import success, warning, info, dim, bold, print_error, CHECK, Spinner, colorize_commit_type

from src.cli.args import parse_args
from src.cli.commands import display_config, run_setup, run_install_completion, run_warmup
from src.cli.utils import clean_commit_message, copy_to_clipboard, display_options, edit_message, TYPES_PATTERN


def _generate_message(client, prompt, timings):
    """Run LLM generation with spinner and return response."""
    t_gen = time.time()
    with Spinner():
        response = client.generate(prompt)
    timings['generate'] = time.time() - t_gen
    return response


def _parse_choose_response(response_content):
    """Parse multi-option response into cleaned options list."""
    parts = re.split(r'\[Option \d+\]\s*', response_content)
    options = [p.strip() for p in parts if p.strip()]

    if len(options) <= 1:
        type_pattern = rf'\n(?=\[?(?:{TYPES_PATTERN})[\(!:])'
        parts = re.split(type_pattern, response_content.strip())
        options = [p.strip() for p in parts if p.strip()]

    cleaned_options = []
    for opt in options:
        opt = clean_commit_message(opt)
        opt = re.sub(rf'^\[?({TYPES_PATTERN})\(', r'\1(', opt)
        lines = opt.split('\n')
        if lines[0].endswith(']'):
            lines[0] = lines[0][:-1]
        cleaned_options.append('\n'.join(lines))

    return cleaned_options if cleaned_options else [clean_commit_message(response_content.strip())]


def _display_file_list(processed, max_shown):
    """Show which files will be analyzed, collapsing long lists.

    Args:
        processed: ProcessedDiff with file_details
        max_shown: Maximum files to display before collapsing (from config)
    """
    if not processed.file_details:
        return
    print(bold("Staged changes:"))
    shown = processed.file_details[:max_shown]
    remaining = len(processed.file_details) - len(shown)
    for path, additions, deletions in shown:
        print(dim(f"  {path} (+{additions} -{deletions})"))
    if remaining > 0:
        print(dim(f"  ... and {remaining} more files"))
    if processed.filtered_files > 0:
        print(dim(f"  {processed.filtered_files} noise files filtered"))


def _display_message(message):
    """Display commit message with horizontal rules and colored type."""
    colored = colorize_commit_type(message)
    lines = colored.split('\n')
    # Use raw message for width calculation (no ANSI codes)
    raw_lines = message.split('\n')
    width = max((len(line) for line in raw_lines), default=40)
    print(f"\n{dim('─' * width)}")
    print(bold(lines[0]))
    for line in lines[1:]:
        print(line)
    print(dim('─' * width))


def _copy_and_report(message, no_copy):
    """Copy message to clipboard and print result."""
    if no_copy:
        return
    copied, reason = copy_to_clipboard(message)
    if copied:
        print(f"{success(CHECK)} Copied to clipboard!")
    else:
        print(f"{warning('!')} Could not copy to clipboard{': ' + reason if reason else ''}")
        print(dim("  Select the message above to copy manually."))


def _handle_subcommands(args):
    """Handle subcommands that exit early.

    Returns:
        tuple: (exit_code, should_exit) - exit_code if should_exit is True
    """
    if args.install_completion:
        return run_install_completion(), True
    if args.display_config:
        return display_config(), True
    if args.setup:
        return run_setup(), True
    return 0, False


def _get_provider_and_model(args, config):
    """Resolve provider and model from args, env, or config.

    Precedence: CLI args > environment variables > config file
    """
    provider = args.provider or os.environ.get('CM_PROVIDER') or config.provider
    model = args.model or os.environ.get('CM_MODEL') or config.model
    return provider, model


def _prepare_staged_changes(is_pipe):
    """Get and validate staged changes from git.

    Returns:
        tuple: (changes, timings_dict) or raises early exit
    """
    timings = {}
    t0 = time.time()
    try:
        analyzer = GitAnalyzer()
        changes = analyzer.get_staged_changes()
    except GitError as e:
        print_error(str(e))
        return None, {'git': time.time() - t0}
    timings['git'] = time.time() - t0

    if changes.is_empty:
        print_error("No staged changes. Run 'git add' first.")
        return None, timings

    return changes, timings


def _initialize_client(provider, model, processed, is_pipe, timings):
    """Initialize LLM client with optional warmup for Ollama.

    Returns:
        tuple: (client, t0) where t0 is the start time for total LLM timing
    """
    t0 = time.time()
    client = get_client(provider=provider, model=model)
    if not is_pipe:
        print(f"Analyzing {bold(str(processed.total_files))} files using {info(client.name)}... ", end='', flush=True)

    if isinstance(client, OllamaClient) and not client._is_model_loaded():
        if not is_pipe:
            print(dim("loading model... "), end='', flush=True)
        t_warmup = time.time()
        warmup_success = client.warmup()
        timings['warmup'] = time.time() - t_warmup
        if not warmup_success and not is_pipe:
            print(warning("warmup failed, generation may be slow... "), end='', flush=True)

    return client, t0


def _handle_response(args, response, is_pipe, client, config):
    """Process LLM response into final commit message.

    Returns:
        tuple: (message, should_return, return_code) - if should_return, exit with return_code
    """
    if args.choose is not None:
        options = _parse_choose_response(response.content)
        if is_pipe:
            message = options[0]
        else:
            idx = display_options(options)
            if idx is None:
                print(dim("Cancelled."))
                return None, True, 0
            message = options[idx]
            print(success("done!"))
    else:
        message = clean_commit_message(response.content.strip())
        if not is_pipe:
            print(success("done!"))

    # Append JIRA ticket if provided
    if args.jira:
        ticket_prefix = args.ticket_prefix or config.ticket_prefix
        ticket_ref = f"{ticket_prefix}: {args.jira.upper()}"
        message = f"{message}\n\n{ticket_ref}"

    return message, False, 0


def _print_verbose_stats(args, is_pipe, prompt, response, timings):
    """Print verbose timing and token statistics."""
    if not args.verbose or is_pipe:
        return
    print()
    print(dim(f"  Prompt: ~{len(prompt)//4} tokens ({len(prompt)} chars)"))
    print(dim(f"  Response: {response.tokens_used} tokens"))
    if response.tokens_used > 0 and timings.get('generate'):
        tok_per_sec = response.tokens_used / timings['generate']
        print(dim(f"  Speed: {tok_per_sec:.1f} tokens/sec"))
    print(dim(f"  Timings: git={timings['git']:.2f}s, diff={timings['diff']:.2f}s, prompt={timings['prompt']:.2f}s, generate={timings.get('generate', 0):.2f}s"))


def _handle_interactive_action(args, message, prompt_config, processed):
    """Handle interactive edit/regenerate prompt.

    Returns:
        tuple: (action, new_message, new_prompt) where action is 'done', 'edited', or 'regenerate'
    """
    try:
        action = input(f"\n{dim('(e)dit, (r)egenerate, or Enter to accept: ')}").strip().lower()
    except (KeyboardInterrupt, EOFError):
        return 'done', message, None

    if action == 'e':
        edited = edit_message(message)
        if edited:
            return 'edited', edited, None
        return 'done', message, None
    elif action == 'r':
        try:
            regen_hint = input(f"{dim('  Hint (Enter to skip): ')}").strip()
        except (KeyboardInterrupt, EOFError):
            return 'done', message, None
        if regen_hint:
            prompt_config.hint = regen_hint
        new_prompt = PromptBuilder().build(processed, prompt_config)
        print(f"\nRegenerating... ", end='', flush=True)
        return 'regenerate', message, new_prompt

    return 'done', message, None


def _generate_commit_flow(args, config, provider, model):
    """Main commit message generation flow.

    Returns:
        int: Exit code
    """
    is_pipe = not sys.stdout.isatty()
    is_interactive = sys.stdin.isatty() and not is_pipe

    # Get staged changes
    changes, timings = _prepare_staged_changes(is_pipe)
    if changes is None:
        return 1

    # Process diff
    t0 = time.time()
    processor = DiffProcessor()
    processed = processor.process(changes)
    timings['diff'] = time.time() - t0

    # Show files being analyzed
    if not is_pipe:
        _display_file_list(processed, config.max_file_display)

    # Build prompt config
    num_options = 1
    if args.choose is not None:
        num_options = max(2, min(args.choose, 4))

    t0 = time.time()
    prompt_config = PromptConfig(
        hint=args.hint,
        forced_type=args.type,
        num_options=num_options,
        file_count=processed.total_files,
        style=config.style,
        include_body=config.include_body,
        max_subject_length=config.max_subject_length,
    )
    prompt = PromptBuilder().build(processed, prompt_config)
    timings['prompt'] = time.time() - t0

    # Initialize LLM client
    try:
        client, t0 = _initialize_client(provider, model, processed, is_pipe, timings)
    except LLMError as e:
        if not is_pipe:
            print()
        print_error(str(e))
        return 1

    # Generation + display loop (supports regeneration)
    while True:
        # Generate
        try:
            response = _generate_message(client, prompt, timings)
            timings['llm_total'] = time.time() - t0
        except LLMError as e:
            if not is_pipe:
                print()
            print_error(str(e))
            return 1

        _print_verbose_stats(args, is_pipe, prompt, response, timings)

        # Handle response
        message, should_return, return_code = _handle_response(args, response, is_pipe, client, config)
        if should_return:
            return return_code

        # Pipe mode: output raw message and exit
        if is_pipe:
            print(message)
            return 0

        # Display and copy
        _display_message(message)
        _copy_and_report(message, args.no_copy)

        # Interactive post-generation prompt
        if not is_interactive:
            break

        action, message, new_prompt = _handle_interactive_action(args, message, prompt_config, processed)
        if action == 'edited':
            _display_message(message)
            _copy_and_report(message, args.no_copy)
            break
        elif action == 'regenerate':
            prompt = new_prompt
            continue
        else:
            break

    return 0


def main() -> int:
    """Main entry point for the CLI."""
    args = parse_args()

    # Handle subcommands that exit early
    exit_code, should_exit = _handle_subcommands(args)
    if should_exit:
        return exit_code

    # Load config and resolve provider/model
    config = load_config()
    provider, model = _get_provider_and_model(args, config)

    # Handle warmup subcommand (needs provider/model)
    if args.warmup:
        return run_warmup(provider, model)

    # Apply CLI overrides to config
    if args.style:
        config.style = args.style
    if args.no_body:
        config.include_body = False

    # Run main generation flow
    return _generate_commit_flow(args, config, provider, model)
