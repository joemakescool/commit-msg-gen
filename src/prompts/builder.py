"""Prompt Builder - Construct LLM prompts for commit message generation."""

from dataclasses import dataclass

from src.git import ProcessedDiff
from src import COMMIT_TYPES


@dataclass
class PromptConfig:
    """User-provided context that shapes the prompt."""
    hint: str | None = None
    forced_type: str | None = None
    num_options: int = 1
    file_count: int = 0
    style: str = "conventional"
    include_body: bool = True
    max_subject_length: int = 50


class PromptBuilder:
    """Constructs prompts optimized for commit message generation."""

    def build(self, diff: ProcessedDiff, config: PromptConfig | None = None) -> str:
        config = config or PromptConfig()
        sections = [
            self._build_role_section(),
            self._build_format_section(config),
            self._build_examples_section(config),
            self._build_diff_section(diff),
            self._build_hints_section(config),
            self._build_analysis_section(),
            self._build_final_instructions(config),
        ]
        return "\n\n".join(filter(None, sections))

    def _build_role_section(self) -> str:
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
        max_len = config.max_subject_length
        is_simple = config.style == "simple"

        if is_simple:
            format_desc = f"subject line (imperative mood, max {max_len} chars)"
            type_instruction = "\nUse a simple, direct subject line without type prefixes."
        else:
            format_desc = f"type(scope): subject line (imperative mood, max {max_len} chars)"
            type_instruction = self._build_type_instruction(config.forced_type)

        body_section = self._build_body_section(config) if config.include_body else \
            "\nDo NOT include a body or bullet points. Subject line only."

        return f"""<format>
Write commit messages in this exact format:

{format_desc}
{body_section}

{type_instruction}
</format>"""

    def _build_type_instruction(self, forced_type: str | None) -> str:
        if forced_type:
            return f"\nIMPORTANT: Use type '{forced_type}' for this commit."
        types_list = "\n".join(f"  - {t}: {desc}" for t, desc in COMMIT_TYPES.items())
        return f"\nChoose the most appropriate type:\n{types_list}"

    def _build_body_section(self, config: PromptConfig) -> str:
        fc = config.file_count

        if config.style == "detailed":
            bullets = self._get_bullet_range(fc, thresholds=[(15, "6-8"), (8, "5-6"), (4, "4-5"), (0, "2-3")])
        else:
            bullets = self._get_bullet_range(fc, thresholds=[(15, "5-6"), (8, "4-5"), (4, "3-4"), (0, "1-2")])

        prefix = "REQUIRED: Write exactly" if fc >= 8 else "Write"
        suffix = "for this large change" if fc >= 15 else "for this change" if fc >= 4 else "for this small change"
        bullet_instruction = f"{prefix} {bullets} bullets {suffix} ({fc} files)."

        return f"""
- bullet points explaining the changes

{bullet_instruction}

Each bullet should:
- Be a complete thought (10-20 words)
- Explain WHAT changed and WHY
- Mention specific files, components, or functions by name"""

    def _get_bullet_range(self, file_count: int, thresholds: list[tuple[int, str]]) -> str:
        for threshold, range_str in thresholds:
            if file_count >= threshold:
                return range_str
        return thresholds[-1][1]

    def _build_examples_section(self, config: PromptConfig) -> str:
        if config.style == "simple":
            if config.include_body:
                return """<examples>
Example 1 - Simple fix:
Handle expired token gracefully

- Return 401 with clear message instead of crashing

Example 2 - Small feature:
Add rate limiting to login endpoint

- Limits to 5 attempts per minute per IP
- Returns 429 with retry-after header when exceeded
</examples>"""
            else:
                return """<examples>
Example 1: Handle expired token gracefully
Example 2: Add rate limiting to login endpoint
Example 3: Extract query builders into separate module
</examples>"""
        elif config.style == "detailed":
            return """<examples>
Example 1 - Fix with context:
fix(auth): handle expired token gracefully in session middleware

- Return 401 with clear error message instead of throwing unhandled exception
- Add specific error code AUTH_TOKEN_EXPIRED for client-side handling
- Log token expiry events for security monitoring

Example 2 - Feature with full detail:
feat(api): add rate limiting to login endpoint with Redis backing

- Implements sliding window rate limit of 5 attempts per minute per IP
- Returns 429 status with Retry-After header when limit exceeded
- Uses Redis for distributed rate limiting across multiple instances
- Adds configuration options for limit thresholds in environment variables
</examples>"""
        else:
            if config.include_body:
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
</examples>"""
            else:
                return """<examples>
Example 1: fix(auth): handle expired token gracefully
Example 2: feat(api): add rate limiting to login endpoint
Example 3: refactor(db): extract query builders into separate module
</examples>"""

    def _build_diff_section(self, diff: ProcessedDiff) -> str:
        parts = [
            "<changes>",
            f"FILES CHANGED: {diff.total_files}",
            "",
            diff.summary,
        ]

        if diff.detailed_diff:
            parts.extend(["", "DIFF DETAILS:", diff.detailed_diff])

        if diff.truncated:
            parts.append("\n[Note: Diff was truncated due to size. Focus on the file summary above for scope.]")

        parts.append("</changes>")
        return "\n".join(parts)

    def _build_hints_section(self, config: PromptConfig) -> str:
        if not config.hint:
            return ""

        return f"""<context>
The developer provided this context about the changes:
"{config.hint}"

Use this to inform your message, but verify it matches what you see in the diff.
</context>"""

    def _build_analysis_section(self) -> str:
        return """<thinking>
Before writing, mentally identify:
1. What is the PRIMARY change? (there's usually one main thing)
2. What type best fits? (feat/fix/refactor/etc.)
3. What's the scope? (affected module/component)
4. What's the key insight a future developer needs?

DO NOT output this analysis. Use it internally, then output ONLY the commit message.
</thinking>"""

    def _build_final_instructions(self, config: PromptConfig) -> str:
        if config.style == "simple":
            format_example = "Subject line here"
        else:
            format_example = "type(scope): subject line"

        if config.num_options > 1:
            body_example = "\n\n- bullet explaining implementation detail" if config.include_body else ""
            body_example2 = "\n\n- bullet explaining user-facing benefit" if config.include_body else ""

            return f"""<instructions>
Generate exactly {config.num_options} SEPARATE commit message options.

Each option MUST take a meaningfully different approach:
- Option 1: Focus on the TECHNICAL change (what was done to the code)
- Option 2: Focus on the USER/BUSINESS impact (why it matters)

Format exactly like this:

[Option 1]
{format_example}{body_example}

[Option 2]
{format_example}{body_example2}

IMPORTANT:
- Include BOTH [Option 1] and [Option 2] labels exactly as shown
- No markdown, no extra explanation, no preamble
</instructions>"""
        else:
            body_rule = "- Include bullet points in the body" if config.include_body else "- Do NOT include a body, subject line only"
            return f"""<instructions>
Generate exactly ONE commit message.

Rules:
- Start directly with the {format_example} line
- No markdown formatting (no ```, no bold)
- No preamble like "Here's a commit message:"
- No explanation after the message
{body_rule}
- Just the raw commit message, ready to use
</instructions>"""
