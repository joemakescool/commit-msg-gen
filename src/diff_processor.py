"""
Diff Processor Module

Responsible for making large diffs LLM-friendly.
Takes raw git output → returns focused, bounded context.

The key insight: LLMs don't need every line to write a good commit message.
They need to understand WHAT changed and WHERE.
"""

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
import re

from git_analyzer import FileChange, StagedChanges


class Priority(IntEnum):
    """
    File priority for inclusion in LLM context.
    
    Lower number = higher priority = included first.
    
    Why these tiers?
    - SOURCE: The actual changes we're committing
    - TEST: Tells us what behavior changed
    - CONFIG: Usually boilerplate but sometimes important
    - DOCS: Rarely affects commit message
    - NOISE: Never include (lock files, generated code)
    """
    SOURCE = 1
    TEST = 2
    CONFIG = 3
    DOCS = 4
    NOISE = 99  # Filtered out entirely


@dataclass
class ProcessedDiff:
    """
    LLM-ready representation of staged changes.
    
    Separates the "summary" (always sent) from "details" (sent if room).
    """
    # Always included - cheap and informative
    summary: str  # File list with +/- counts
    
    # Included up to token budget
    detailed_diff: str  # Actual diff content for important files
    
    # Metadata for debugging/display
    total_files: int = 0
    included_files: int = 0
    filtered_files: int = 0
    truncated: bool = False
    
    @property
    def estimated_tokens(self) -> int:
        """Rough token estimate (~4 chars per token)."""
        total_chars = len(self.summary) + len(self.detailed_diff)
        return total_chars // 4


@dataclass 
class ProcessorConfig:
    """
    Tunable settings for diff processing.
    
    Why a config object?
    - Easy to test with different settings
    - Could load from file later
    - Clear what's configurable vs hardcoded
    """
    # Token budget for the diff portion of the prompt
    # (Leave room for system prompt + response)
    max_tokens: int = 3000
    
    # Max lines of diff per file (catch runaway files)
    max_lines_per_file: int = 200
    
    # Files bigger than this get summary only
    large_file_threshold: int = 100


class DiffProcessor:
    """
    Transforms raw git diff into LLM-friendly context.
    
    Strategy:
    1. Classify each file by priority
    2. Filter out noise (lock files, generated code)
    3. Sort by priority
    4. Include full diffs until budget exhausted
    5. Include summary for everything else
    """
    
    # Patterns for files to completely ignore
    NOISE_PATTERNS: list[str] = [
        # Lock files
        r'package-lock\.json$',
        r'yarn\.lock$',
        r'pnpm-lock\.yaml$',
        r'poetry\.lock$',
        r'Cargo\.lock$',
        r'Gemfile\.lock$',
        r'composer\.lock$',
        
        # Generated/compiled
        r'\.min\.js$',
        r'\.min\.css$',
        r'\.map$',
        r'\.pyc$',
        r'__pycache__',
        r'\.class$',
        r'dist/',
        r'build/',
        r'\.egg-info/',
        
        # IDE/editor
        r'\.idea/',
        r'\.vscode/',
        r'\.DS_Store$',
        
        # Dependencies (vendored)
        r'node_modules/',
        r'vendor/',
        r'venv/',
        r'\.venv/',
    ]
    
    # Patterns for test files
    TEST_PATTERNS: list[str] = [
        r'test[s]?/',
        r'spec[s]?/',
        r'__tests__/',
        r'\.test\.',
        r'\.spec\.',
        r'_test\.',
        r'_spec\.',
        r'Test\.java$',
        r'Tests\.java$',
    ]
    
    # Patterns for config files
    CONFIG_PATTERNS: list[str] = [
        r'\.json$',
        r'\.ya?ml$',
        r'\.toml$',
        r'\.ini$',
        r'\.env',
        r'\.config\.',
        r'config/',
        r'settings/',
        r'Makefile$',
        r'Dockerfile$',
        r'docker-compose',
    ]
    
    # Patterns for documentation
    DOCS_PATTERNS: list[str] = [
        r'\.md$',
        r'\.rst$',
        r'\.txt$',
        r'docs/',
        r'README',
        r'CHANGELOG',
        r'LICENSE',
    ]
    
    def __init__(self, config: ProcessorConfig | None = None):
        self.config = config or ProcessorConfig()
        
        # Compile patterns once for performance
        self._noise_re = [re.compile(p, re.IGNORECASE) for p in self.NOISE_PATTERNS]
        self._test_re = [re.compile(p, re.IGNORECASE) for p in self.TEST_PATTERNS]
        self._config_re = [re.compile(p, re.IGNORECASE) for p in self.CONFIG_PATTERNS]
        self._docs_re = [re.compile(p, re.IGNORECASE) for p in self.DOCS_PATTERNS]
    
    def process(self, changes: StagedChanges) -> ProcessedDiff:
        """
        Main entry point: raw changes → LLM-ready context.
        """
        # Step 1: Classify and filter
        classified = self._classify_files(changes.files)
        filtered = [(f, p) for f, p in classified if p != Priority.NOISE]
        noise_count = len(classified) - len(filtered)
        
        # Step 2: Sort by priority (most important first)
        filtered.sort(key=lambda x: (x[1], -x[0].total_changes))
        
        # Step 3: Build summary (always included)
        summary = self._build_summary(filtered, noise_count)
        
        # Step 4: Build detailed diff (budget-limited)
        detailed_diff, included_count, truncated = self._build_detailed_diff(
            filtered, 
            changes.diff
        )
        
        return ProcessedDiff(
            summary=summary,
            detailed_diff=detailed_diff,
            total_files=len(changes.files),
            included_files=included_count,
            filtered_files=noise_count,
            truncated=truncated
        )
    
    def _classify_files(self, files: list[FileChange]) -> list[tuple[FileChange, Priority]]:
        """Assign a priority to each file based on path patterns."""
        return [(f, self._get_priority(f.path)) for f in files]
    
    def _get_priority(self, path: str) -> Priority:
        """
        Determine file priority from its path.
        
        Order matters: check noise first (to exclude),
        then most specific patterns.
        """
        # Check noise first - these get filtered out
        if any(p.search(path) for p in self._noise_re):
            return Priority.NOISE
        
        # Check specific categories
        if any(p.search(path) for p in self._test_re):
            return Priority.TEST
        
        if any(p.search(path) for p in self._docs_re):
            return Priority.DOCS
            
        if any(p.search(path) for p in self._config_re):
            return Priority.CONFIG
        
        # Default: assume it's source code (most important)
        return Priority.SOURCE
    
    def _build_summary(
        self, 
        files: list[tuple[FileChange, Priority]], 
        noise_count: int
    ) -> str:
        """
        Build a compact summary of all changes.
        
        This is ALWAYS sent to the LLM - it's cheap and gives
        the big picture even if we can't include full diffs.
        """
        lines = ["FILES CHANGED:"]
        
        current_priority = None
        for file, priority in files:
            # Add section header when priority changes
            if priority != current_priority:
                current_priority = priority
                label = {
                    Priority.SOURCE: "Source",
                    Priority.TEST: "Tests", 
                    Priority.CONFIG: "Config",
                    Priority.DOCS: "Docs",
                }.get(priority, "Other")
                lines.append(f"\n[{label}]")
            
            # File entry with change counts
            lines.append(f"  {file.path} (+{file.additions} -{file.deletions})")
        
        if noise_count > 0:
            lines.append(f"\n[Filtered: {noise_count} files (lock files, generated code)]")
        
        return "\n".join(lines)
    
    def _build_detailed_diff(
        self,
        files: list[tuple[FileChange, Priority]],
        full_diff: str
    ) -> tuple[str, int, bool]:
        """
        Extract relevant portions of the diff within token budget.
        
        Returns: (diff_text, files_included, was_truncated)
        """
        if not full_diff:
            return "", 0, False
        
        # Parse the full diff into per-file chunks
        file_diffs = self._split_diff_by_file(full_diff)
        
        result_parts = []
        tokens_used = 0
        files_included = 0
        truncated = False
        
        for file, priority in files:
            if file.path not in file_diffs:
                continue
            
            file_diff = file_diffs[file.path]
            
            # Truncate huge files
            file_diff = self._truncate_file_diff(file_diff, file.path)
            
            # Check token budget
            diff_tokens = len(file_diff) // 4
            if tokens_used + diff_tokens > self.config.max_tokens:
                truncated = True
                break
            
            result_parts.append(file_diff)
            tokens_used += diff_tokens
            files_included += 1
        
        return "\n".join(result_parts), files_included, truncated
    
    def _split_diff_by_file(self, diff: str) -> dict[str, str]:
        """
        Split a unified diff into per-file chunks.
        
        Diffs start with 'diff --git a/path b/path'
        """
        files = {}
        current_file = None
        current_lines = []
        
        for line in diff.split('\n'):
            if line.startswith('diff --git'):
                # Save previous file
                if current_file:
                    files[current_file] = '\n'.join(current_lines)
                
                # Extract filename from 'diff --git a/path b/path'
                match = re.search(r'diff --git a/(.+?) b/', line)
                if match:
                    current_file = match.group(1)
                    current_lines = [line]
            elif current_file:
                current_lines.append(line)
        
        # Don't forget the last file
        if current_file:
            files[current_file] = '\n'.join(current_lines)
        
        return files
    
    def _truncate_file_diff(self, diff: str, path: str) -> str:
        """
        Truncate a single file's diff if it's too long.
        
        Keeps the header and first N lines, adds truncation notice.
        """
        lines = diff.split('\n')
        
        if len(lines) <= self.config.max_lines_per_file:
            return diff
        
        truncated_lines = lines[:self.config.max_lines_per_file]
        truncated_lines.append(f"\n... [{len(lines) - self.config.max_lines_per_file} more lines truncated from {path}]")
        
        return '\n'.join(truncated_lines)


# Quick test when run directly
if __name__ == "__main__":
    from git_analyzer import GitAnalyzer, GitError
    
    try:
        analyzer = GitAnalyzer()
        changes = analyzer.get_staged_changes()
        
        if changes.is_empty:
            print("No staged changes")
        else:
            processor = DiffProcessor()
            processed = processor.process(changes)
            
            print("=== SUMMARY ===")
            print(processed.summary)
            print(f"\n=== STATS ===")
            print(f"Total files: {processed.total_files}")
            print(f"Included in diff: {processed.included_files}")
            print(f"Filtered out: {processed.filtered_files}")
            print(f"Truncated: {processed.truncated}")
            print(f"Estimated tokens: {processed.estimated_tokens}")
            print(f"\n=== DETAILED DIFF (first 500 chars) ===")
            print(processed.detailed_diff[:500])
            if len(processed.detailed_diff) > 500:
                print("...")
                
    except GitError as e:
        print(f"Error: {e}")
