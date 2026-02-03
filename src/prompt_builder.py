"""
Prompt Builder Module

Responsible for constructing effective LLM prompts.
Single Responsibility: Turn processed diff → prompt string.

The prompt is the most important part of this tool.
A good prompt = good commit messages.
"""

from dataclasses import dataclass

from src.diff_processor import ProcessedDiff
from src import COMMIT_TYPES  # Centralized in __init__.py


@dataclass
class PromptConfig:
    """
    User-provided context that shapes the prompt.

    These come from CLI flags like --hint and --type.
    """
    hint: str | None = None          # User context: "refactoring auth"
    forced_type: str | None = None   # Force: feat, fix, refactor, etc.
    num_options: int = 1             # How many messages to generate
    file_count: int = 0              # Number of files changed (for bullet scaling)


class PromptBuilder:
    """
    Constructs prompts optimized for commit message generation.
    
    Design decisions:
    - Clear structure with XML-ish tags (Claude handles these well)
    - Examples embedded in prompt (few-shot learning)
    - Explicit format requirements
    """
    
    def build(self, diff: ProcessedDiff, config: PromptConfig | None = None) -> str:
        """
        Build the complete prompt for the LLM.

        Structure:
        1. Role & task description
        2. Output format requirements
        3. Examples (few-shot)
        4. The actual diff
        5. User hints (if any)
        6. Analysis step (chain-of-thought)
        7. Final instructions
        """
        config = config or PromptConfig()

        sections = [
            self._build_role_section(),
            self._build_format_section(config),
            self._build_examples_section(),
            self._build_diff_section(diff),
            self._build_hints_section(config),
            self._build_analysis_section(),
            self._build_final_instructions(config),
        ]

        return "\n\n".join(filter(None, sections))
    
    def _build_role_section(self) -> str:
        """Set up the LLM's role and task."""
        return """You are a senior software engineer who has mass-reviewed thousands of pull requests and written commit messages for large open-source projects. You deeply understand that commit messages are documentation for future developers—often yourself, six months from now, wondering "why did we do this?"

Your philosophy on commit messages:
- The DIFF shows WHAT changed. Your job is to explain WHY.
- A good commit message saves 15 minutes of code archaeology later.
- Write for the tired developer at 2am debugging a production issue.
- Every word must earn its place. No filler, no fluff.

Your approach:
1. First, identify the PRIMARY purpose of this change (there's usually one main thing)
2. Determine the scope—what module, component, or area is affected
3. Write a subject line that completes the sentence: "If applied, this commit will..."
4. Add bullets that explain impact, reasoning, or non-obvious details

What you NEVER do:
- Use vague verbs: "Update", "Change", "Modify", "Fix stuff" (be specific)
- State the obvious: "Change X to Y" when the diff shows exactly that
- Write bullets that just repeat the subject line in different words
- Start bullets with "This commit..." (implied—it's a commit message)
- Add filler bullets just to hit a count (quality over quantity)

The scope in type(scope) should be:
- A module name: auth, api, db, ui
- A feature area: login, checkout, search
- A component: Button, UserService, config
- Keep it short (1 word ideal, 2 max)"""
    
    def _build_format_section(self, config: PromptConfig) -> str:
        """Specify the exact output format we want."""
        type_instruction = ""
        if config.forced_type:
            type_instruction = f"\nIMPORTANT: Use type '{config.forced_type}' for this commit."
        else:
            types_list = "\n".join(f"  - {t}: {desc}" for t, desc in COMMIT_TYPES.items())
            type_instruction = f"\nChoose the most appropriate type:\n{types_list}"
        
        # Determine bullet count based on file count
        fc = config.file_count
        if fc >= 15:
            bullet_instruction = f"REQUIRED: Write exactly 5-6 bullets for this large change ({fc} files)."
        elif fc >= 8:
            bullet_instruction = f"REQUIRED: Write exactly 4-5 bullets for this change ({fc} files)."
        elif fc >= 4:
            bullet_instruction = f"Write 3-4 bullets for this change ({fc} files)."
        else:
            bullet_instruction = f"Write 1-2 bullets for this small change ({fc} files)."
        
        return f"""<format>
Write commit messages in this exact format:

type(scope): subject line (imperative mood, max 50 chars)

- bullet points explaining the changes

{type_instruction}

{bullet_instruction}

Each bullet should:
- Be a complete thought (10-20 words)
- Explain WHAT changed and WHY
- Mention specific files, components, or functions by name
</format>"""
    
    def _build_examples_section(self) -> str:
        """Provide few-shot examples of good commit messages."""
        return """<examples>
Example 1 - Simple fix (1 bullet):
fix(auth): handle expired token gracefully

- Return 401 with clear message instead of crashing

Example 2 - Small feature (2 bullets):
feat(api): add rate limiting to login endpoint

- Limits to 5 attempts per minute per IP
- Returns 429 with retry-after header when exceeded

Example 3 - Medium refactor (3 bullets):
refactor(db): extract query builders into separate module

- Moved complex queries from UserService to QueryBuilder class
- Reduces duplication across 4 service files
- Makes query logic easier to test in isolation

Example 4 - Large feature (4-5 bullets):
feat(upload): add batch file processing

- New BatchUploadService handles multiple files in single request
- Chunked processing keeps memory usage under 100MB
- Progress events emitted for UI feedback
- Failed files don't block successful ones
- Added cleanup job for incomplete uploads

Example 5 - Tiny change (1 bullet):
chore(deps): bump lodash to 4.17.21

- Fixes prototype pollution vulnerability CVE-2021-23337
</examples>"""
    
    def _build_diff_section(self, diff: ProcessedDiff) -> str:
        """Include the actual changes."""
        parts = [
            "<changes>",
            f"FILES CHANGED: {diff.total_files}",
            "",
            diff.summary,
        ]
        
        if diff.detailed_diff:
            parts.extend([
                "",
                "DIFF DETAILS:",
                diff.detailed_diff,
            ])
        
        if diff.truncated:
            parts.append(
                "\n[Note: Diff was truncated due to size. "
                "Focus on the file summary above for scope.]"
            )
        
        parts.append("</changes>")
        
        return "\n".join(parts)
    
    def _build_hints_section(self, config: PromptConfig) -> str:
        """Include user-provided context if any."""
        if not config.hint:
            return ""
        
        return f"""<context>
The developer provided this context about the changes:
"{config.hint}"

Use this to inform your message, but verify it matches what you see in the diff.
</context>"""
    
    def _build_analysis_section(self) -> str:
        """Add chain-of-thought reasoning to improve output quality."""
        return """<thinking>
Before writing, mentally identify:
1. What is the PRIMARY change? (there's usually one main thing)
2. What type best fits? (feat/fix/refactor/etc.)
3. What's the scope? (affected module/component)
4. What's the key insight a future developer needs?

DO NOT output this analysis. Use it internally, then output ONLY the commit message.
</thinking>"""

    def _build_final_instructions(self, config: PromptConfig) -> str:
        """Clear instructions for what to output."""
        if config.num_options > 1:
            return f"""<instructions>
Generate exactly {config.num_options} SEPARATE commit message options.

Each option MUST take a meaningfully different approach:
- Option 1: Focus on the TECHNICAL change (what was done to the code)
- Option 2: Focus on the USER/BUSINESS impact (why it matters)

Format exactly like this:

[Option 1]
type(scope): technical-focused subject line

- bullet explaining implementation detail
- bullet about code structure change

[Option 2]
type(scope): impact-focused subject line

- bullet explaining user-facing benefit
- bullet about problem solved

IMPORTANT:
- Include BOTH [Option 1] and [Option 2] labels exactly as shown
- Same type is OK if both options genuinely fit that type
- Different scopes are OK if the change spans areas
- No markdown, no extra explanation, no preamble
</instructions>"""
        else:
            return """<instructions>
Generate exactly ONE commit message.

Rules:
- Start directly with the type(scope): line
- No markdown formatting (no ```, no bold)
- No preamble like "Here's a commit message:"
- No explanation after the message
- Just the raw commit message, ready to use
</instructions>"""


# Quick test when run directly
if __name__ == "__main__":
    from src.git_analyzer import GitAnalyzer, GitError
    from src.diff_processor import DiffProcessor
    
    try:
        # Get and process changes
        analyzer = GitAnalyzer()
        changes = analyzer.get_staged_changes()
        
        if changes.is_empty:
            print("No staged changes")
        else:
            processor = DiffProcessor()
            processed = processor.process(changes)
            
            # Build prompt with some example config
            builder = PromptBuilder()
            
            # Test 1: Default (single message)
            prompt = builder.build(processed)
            print("=== PROMPT (single message mode) ===")
            print(f"Length: {len(prompt)} chars (~{len(prompt)//4} tokens)")
            print("\n" + prompt[:1500] + "\n...\n")
            
            # Test 2: With hint and forced type
            config = PromptConfig(
                hint="refactoring the git analysis logic",
                forced_type="refactor",
                num_options=2
            )
            prompt_with_config = builder.build(processed, config)
            print("\n=== PROMPT (with config) ===")
            print(f"Length: {len(prompt_with_config)} chars")
            
    except GitError as e:
        print(f"Error: {e}")
