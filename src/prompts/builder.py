"""Prompt Builder - Construct LLM prompts for commit message generation."""

from dataclasses import dataclass

from src.git import ProcessedDiff
from src import COMMIT_TYPES

# Bullet count thresholds by file count: (min_files, bullet_range)
# Larger changes need more bullets to explain scope
BULLET_THRESHOLDS_DETAILED = [
    (15, "6-8"),  # 15+ files: large refactoring
    (8, "5-6"),   # 8-14 files: medium change
    (4, "4-5"),   # 4-7 files: small multi-file
    (0, "2-3"),   # 1-3 files: focused change
]

BULLET_THRESHOLDS_DEFAULT = [
    (15, "5-6"),
    (8, "4-5"),
    (4, "3-4"),
    (0, "1-2"),
]

# File count size descriptors
FILE_SIZE_THRESHOLDS = [
    (15, "large"),
    (4, ""),
    (0, "small"),
]

# Example template components
_SUBJECT_SIMPLE = "[subject: imperative verb + what changed]"
_SUBJECT_TYPED = "type(scope): [imperative verb + what changed]"

_BULLETS_SIMPLE = """\
- [bullet: specific detail from the diff]
- [bullet: another detail if needed]"""

_BULLETS_CONVENTIONAL = """\
- [bullet: specific detail from the diff]
- [bullet: why or impact if relevant]"""

_BULLETS_DETAILED = """\
- [bullet: specific implementation detail]
- [bullet: why this approach was chosen]
- [bullet: what problem this solves]
- [bullet: any notable side effects]"""

# Lookup table: (style, include_body) -> (subject_template, body_template or None)
EXAMPLE_TEMPLATES: dict[tuple[str, bool], tuple[str, str | None]] = {
    ("simple", True): (_SUBJECT_SIMPLE, _BULLETS_SIMPLE),
    ("simple", False): (_SUBJECT_SIMPLE, None),
    ("detailed", True): (_SUBJECT_TYPED, _BULLETS_DETAILED),
    ("detailed", False): (_SUBJECT_TYPED, _BULLETS_DETAILED),  # detailed always has body
    ("conventional", True): (_SUBJECT_TYPED, _BULLETS_CONVENTIONAL),
    ("conventional", False): (_SUBJECT_TYPED, None),
}


@dataclass
class PromptConfig:
    """User-provided context that shapes the prompt."""
    hint: str | None = None
    forced_type: str | None = None
    num_options: int = 1
    file_count: int = 0
    style: str = "conventional"
    include_body: bool = True
    max_subject_length: int = 72


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
        return """You are an expert at writing git commit messages. Your commit messages are documentation for future developers.

Core principles:
- The DIFF shows WHAT changed. Your job is to explain WHY.
- Write for the developer debugging this at 2am, six months from now.
- Every word must earn its place—no filler.

Your approach:
1. Identify the PRIMARY purpose (commits should do one thing well)
2. If the commit does multiple things, focus on the most significant change
3. Write a subject that completes: "If applied, this commit will..."
4. Add bullets only for non-obvious details, impact, or reasoning

Avoid:
- Vague verbs: "Update", "Change", "Modify" (be specific: "Add", "Remove", "Replace", "Extract")
- Restating the diff: don't say "Change X to Y" when the code shows that
- Filler bullets that repeat the subject line in different words

Scope selection (for type(scope): format):
- ALWAYS include a scope in parentheses — e.g. feat(auth):, fix(api):, refactor(cli):
- Use ONE WORD: module name (auth, api, cli), feature (login, checkout), or component (Button, config)
- NEVER use file paths like 'cli/utils.py' or 'src/config' - just use 'cli' or 'config'
- When changes span multiple areas, pick the primary one"""

    def _build_format_section(self, config: PromptConfig) -> str:
        max_len = config.max_subject_length
        is_simple = config.style == "simple"

        if is_simple:
            format_desc = f"subject line (lowercase, imperative mood, max {max_len} chars)"
            type_instruction = "\nUse a simple, direct subject line without type prefixes."
        else:
            format_desc = f"type(scope): subject line (lowercase, imperative mood, max {max_len} chars)"
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
        thresholds = BULLET_THRESHOLDS_DETAILED if config.style == "detailed" else BULLET_THRESHOLDS_DEFAULT
        bullets = self._get_bullet_range(fc, thresholds)

        prefix = "REQUIRED: Write exactly" if fc >= 8 else "Write"
        size = self._get_bullet_range(fc, FILE_SIZE_THRESHOLDS)
        suffix = f"for this {size} change" if size else "for this change"
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
        warning = "CRITICAL: These show FORMAT only. Never use words from these examples. Analyze the ACTUAL diff below."

        key = (config.style, config.include_body)
        subject, bullets = EXAMPLE_TEMPLATES.get(key, EXAMPLE_TEMPLATES[("conventional", True)])

        example = subject
        if bullets:
            example += "\n\n" + bullets

        return f"""<format-examples>
{warning}

{example}
</format-examples>"""

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
Before writing, analyze:
1. What is the PRIMARY change? Look for: new capability (feat), bug fix (fix), restructuring without behavior change (refactor), or other
2. Is there user-visible impact? If yes, lean toward feat/fix. If purely internal, consider refactor/chore
3. What scope is most affected? Pick the most specific area
4. What would a future developer need to understand about WHY this change was made?

Use this analysis internally, then output ONLY the commit message.
</thinking>"""

    def _build_final_instructions(self, config: PromptConfig) -> str:
        if config.num_options > 1:
            return self._build_multi_option_instructions(config)
        return self._build_single_option_instructions(config)

    def _get_format_example(self, config: PromptConfig) -> str:
        """Return the format example string based on style."""
        return "Subject line here" if config.style == "simple" else "type(scope): subject line"

    def _get_approach_instructions(self, num_options: int) -> str:
        """Return approach guidance based on number of options."""
        if num_options == 2:
            return """Each option MUST take a meaningfully different approach:
- Option 1: Focus on the TECHNICAL change (what was done to the code)
- Option 2: Focus on the USER/BUSINESS impact (why it matters)"""
        return "Each option MUST take a meaningfully different angle on the change."

    def _build_single_option_instructions(self, config: PromptConfig) -> str:
        format_example = self._get_format_example(config)
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

    def _build_multi_option_instructions(self, config: PromptConfig) -> str:
        n = config.num_options
        format_example = self._get_format_example(config)
        body_example = "\n\n- bullet explaining the change" if config.include_body else ""
        approach_instructions = self._get_approach_instructions(n)

        option_labels = "\n\n".join(
            f"[Option {i}]\n{format_example}{body_example}" for i in range(1, n + 1)
        )
        label_list = ", ".join(f"[Option {i}]" for i in range(1, n + 1))

        return f"""<instructions>
Generate exactly {n} SEPARATE commit message options.

{approach_instructions}

Format exactly like this:

{option_labels}

IMPORTANT:
- Include ALL {label_list} labels exactly as shown
- No markdown, no extra explanation, no preamble
</instructions>"""
