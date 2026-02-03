"""LLM Base Classes and Shared Code"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src import COMMIT_TYPE_NAMES


SYSTEM_PROMPT = """You are a senior software engineer specialized in writing precise, informative git commit messages. You have mass-reviewed thousands of pull requests at major tech companies and open-source projects.

Your expertise:
- Deep understanding of conventional commit format (type, scope, subject, body)
- Ability to identify the PRIMARY purpose of a change from a diff
- Writing for future developers who will read git log at 2am debugging production

Your standards:
- Every word earns its place—no filler, no fluff
- The diff shows WHAT; you explain WHY
- Specific verbs over vague ones (never "update", "change", "modify")
- Bullets add context the subject line can't capture"""


def validate_commit_message(content: str) -> tuple[bool, str]:
    """Validate that response looks like a proper commit message."""
    if not content or len(content.strip()) < 10:
        return False, "Response too short"

    types_pattern = '|'.join(COMMIT_TYPE_NAMES)
    pattern = rf'^({types_pattern})(\(.+\))?!?:'
    first_line = content.strip().split('\n')[0]

    if not re.match(pattern, first_line):
        return False, f"Missing conventional commit format. Got: {first_line[:50]}"

    return True, ""


@dataclass
class LLMResponse:
    """Structured response from any LLM provider."""
    content: str
    model: str = ""
    tokens_used: int = 0


class LLMError(Exception):
    """Raised when LLM operations fail."""
    pass


class LLMClient(ABC):
    """Abstract base for LLM clients."""

    @abstractmethod
    def generate(self, prompt: str) -> LLMResponse:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass
