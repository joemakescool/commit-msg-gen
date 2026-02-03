"""Git Analyzer - Extract staged changes from git."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileChange:
    """Represents a single file's changes."""
    path: str
    additions: int
    deletions: int

    @property
    def total_changes(self) -> int:
        return self.additions + self.deletions

    @property
    def directory(self) -> str:
        """Extract the top-level directory for scope detection."""
        parts = Path(self.path).parts
        if len(parts) > 1 and parts[0] in ('src', 'lib', 'app'):
            return parts[1] if len(parts) > 1 else parts[0]
        return parts[0] if parts else ''


@dataclass
class StagedChanges:
    """Complete picture of what's staged for commit."""
    files: list[FileChange] = field(default_factory=list)
    diff: str = ""

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_additions(self) -> int:
        return sum(f.additions for f in self.files)

    @property
    def total_deletions(self) -> int:
        return sum(f.deletions for f in self.files)

    @property
    def is_empty(self) -> bool:
        return len(self.files) == 0


class GitError(Exception):
    """Raised when git operations fail."""
    pass


class GitAnalyzer:
    """Extracts staged changes from git."""

    def __init__(self):
        self._verify_git_available()
        self._verify_in_repo()

    def _run_git(self, *args: str) -> str:
        """Run a git command and return stdout."""
        try:
            result = subprocess.run(
                ['git', *args],
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8',
                errors='replace'
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise GitError(f"Git command failed: git {' '.join(args)}\n{e.stderr}")
        except FileNotFoundError:
            raise GitError("Git is not installed or not in PATH")

    def _verify_git_available(self) -> None:
        """Fail fast if git isn't available."""
        try:
            self._run_git('--version')
        except GitError:
            raise GitError("Git is not installed or not in PATH")

    def _verify_in_repo(self) -> None:
        """Fail fast if we're not in a git repository."""
        try:
            self._run_git('rev-parse', '--git-dir')
        except GitError:
            raise GitError("Not inside a git repository")

    def get_staged_changes(self) -> StagedChanges:
        """Get staged changes only."""
        files = self._get_staged_files()
        diff = self._get_staged_diff()
        return StagedChanges(files=files, diff=diff)

    def _get_staged_files(self) -> list[FileChange]:
        """Parse 'git diff --staged --numstat' output."""
        output = self._run_git('diff', '--staged', '--numstat')

        if not output.strip():
            return []

        files = []
        for line in output.strip().split('\n'):
            parts = line.split('\t')
            if len(parts) >= 3:
                additions = int(parts[0]) if parts[0] != '-' else 0
                deletions = int(parts[1]) if parts[1] != '-' else 0
                path = parts[2]
                files.append(FileChange(path=path, additions=additions, deletions=deletions))

        return files

    def _get_staged_diff(self) -> str:
        """Get the actual diff content for staged changes."""
        return self._run_git('diff', '--staged')
