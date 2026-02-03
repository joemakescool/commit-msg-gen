"""Diff Processor - Transform git diffs into LLM-friendly context."""

from dataclasses import dataclass
from enum import IntEnum
import re

from src.git.analyzer import FileChange, StagedChanges


class Priority(IntEnum):
    """File priority for inclusion in LLM context."""
    SOURCE = 1
    TEST = 2
    CONFIG = 3
    DOCS = 4
    NOISE = 99


@dataclass
class ProcessedDiff:
    """LLM-ready representation of staged changes."""
    summary: str
    detailed_diff: str
    total_files: int = 0
    included_files: int = 0
    filtered_files: int = 0
    truncated: bool = False

    @property
    def estimated_tokens(self) -> int:
        """Rough token estimate (~4 chars per token)."""
        return (len(self.summary) + len(self.detailed_diff)) // 4


@dataclass
class ProcessorConfig:
    """Tunable settings for diff processing."""
    max_tokens: int = 3000
    max_lines_per_file: int = 200
    large_file_threshold: int = 100


class DiffProcessor:
    """Transforms raw git diff into LLM-friendly context."""

    NOISE_PATTERNS: list[str] = [
        r'package-lock\.json$', r'yarn\.lock$', r'pnpm-lock\.yaml$',
        r'poetry\.lock$', r'Cargo\.lock$', r'Gemfile\.lock$', r'composer\.lock$',
        r'\.min\.js$', r'\.min\.css$', r'\.map$', r'\.pyc$', r'__pycache__',
        r'\.class$', r'dist/', r'build/', r'\.egg-info/',
        r'\.idea/', r'\.vscode/', r'\.DS_Store$',
        r'node_modules/', r'vendor/', r'venv/', r'\.venv/',
    ]

    TEST_PATTERNS: list[str] = [
        r'test[s]?/', r'spec[s]?/', r'__tests__/',
        r'\.test\.', r'\.spec\.', r'_test\.', r'_spec\.',
        r'Test\.java$', r'Tests\.java$',
    ]

    CONFIG_PATTERNS: list[str] = [
        r'\.json$', r'\.ya?ml$', r'\.toml$', r'\.ini$', r'\.env',
        r'\.config\.', r'config/', r'settings/',
        r'Makefile$', r'Dockerfile$', r'docker-compose',
    ]

    DOCS_PATTERNS: list[str] = [
        r'\.md$', r'\.rst$', r'\.txt$', r'docs/',
        r'README', r'CHANGELOG', r'LICENSE',
    ]

    def __init__(self, config: ProcessorConfig | None = None):
        self.config = config or ProcessorConfig()
        self._noise_re = [re.compile(p, re.IGNORECASE) for p in self.NOISE_PATTERNS]
        self._test_re = [re.compile(p, re.IGNORECASE) for p in self.TEST_PATTERNS]
        self._config_re = [re.compile(p, re.IGNORECASE) for p in self.CONFIG_PATTERNS]
        self._docs_re = [re.compile(p, re.IGNORECASE) for p in self.DOCS_PATTERNS]

    def process(self, changes: StagedChanges) -> ProcessedDiff:
        """Main entry point: raw changes -> LLM-ready context."""
        classified = self._classify_files(changes.files)
        filtered = [(f, p) for f, p in classified if p != Priority.NOISE]
        noise_count = len(classified) - len(filtered)

        filtered.sort(key=lambda x: (x[1], -x[0].total_changes))

        summary = self._build_summary(filtered, noise_count)
        detailed_diff, included_count, truncated = self._build_detailed_diff(filtered, changes.diff)

        return ProcessedDiff(
            summary=summary,
            detailed_diff=detailed_diff,
            total_files=len(changes.files),
            included_files=included_count,
            filtered_files=noise_count,
            truncated=truncated
        )

    def _classify_files(self, files: list[FileChange]) -> list[tuple[FileChange, Priority]]:
        return [(f, self._get_priority(f.path)) for f in files]

    def _get_priority(self, path: str) -> Priority:
        if any(p.search(path) for p in self._noise_re):
            return Priority.NOISE
        if any(p.search(path) for p in self._test_re):
            return Priority.TEST
        if any(p.search(path) for p in self._docs_re):
            return Priority.DOCS
        if any(p.search(path) for p in self._config_re):
            return Priority.CONFIG
        return Priority.SOURCE

    def _build_summary(self, files: list[tuple[FileChange, Priority]], noise_count: int) -> str:
        lines = ["FILES CHANGED:"]
        current_priority = None

        for file, priority in files:
            if priority != current_priority:
                current_priority = priority
                label = {
                    Priority.SOURCE: "Source",
                    Priority.TEST: "Tests",
                    Priority.CONFIG: "Config",
                    Priority.DOCS: "Docs",
                }.get(priority, "Other")
                lines.append(f"\n[{label}]")
            lines.append(f"  {file.path} (+{file.additions} -{file.deletions})")

        if noise_count > 0:
            lines.append(f"\n[Filtered: {noise_count} files (lock files, generated code)]")

        return "\n".join(lines)

    def _build_detailed_diff(self, files: list[tuple[FileChange, Priority]], full_diff: str) -> tuple[str, int, bool]:
        if not full_diff:
            return "", 0, False

        file_diffs = self._split_diff_by_file(full_diff)
        result_parts = []
        tokens_used = 0
        files_included = 0
        truncated = False

        for file, priority in files:
            if file.path not in file_diffs:
                continue

            file_diff = self._truncate_file_diff(file_diffs[file.path], file.path)
            diff_tokens = len(file_diff) // 4

            if tokens_used + diff_tokens > self.config.max_tokens:
                truncated = True
                break

            result_parts.append(file_diff)
            tokens_used += diff_tokens
            files_included += 1

        return "\n".join(result_parts), files_included, truncated

    def _split_diff_by_file(self, diff: str) -> dict[str, str]:
        files = {}
        current_file = None
        current_lines = []

        for line in diff.split('\n'):
            if line.startswith('diff --git'):
                if current_file:
                    files[current_file] = '\n'.join(current_lines)
                match = re.search(r'diff --git a/(.+?) b/', line)
                if match:
                    current_file = match.group(1)
                    current_lines = [line]
            elif current_file:
                current_lines.append(line)

        if current_file:
            files[current_file] = '\n'.join(current_lines)

        return files

    def _truncate_file_diff(self, diff: str, path: str) -> str:
        lines = diff.split('\n')
        if len(lines) <= self.config.max_lines_per_file:
            return diff

        truncated_lines = lines[:self.config.max_lines_per_file]
        truncated_lines.append(f"\n... [{len(lines) - self.config.max_lines_per_file} more lines truncated from {path}]")
        return '\n'.join(truncated_lines)
