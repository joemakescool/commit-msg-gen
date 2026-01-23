"""
Git Analyzer Module

Responsible for extracting staged changes from git.
Single Responsibility: Talk to git, return structured data.
"""

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
        # Return first meaningful directory (skip 'src' if present)
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
    """
    Extracts staged changes from git.
    
    Why a class? We might want to:
    - Cache results across multiple calls
    - Add configuration (e.g., custom git path)
    - Mock easily in tests
    """
    
    def __init__(self):
        self._verify_git_available()
        self._verify_in_repo()
    
    def _run_git(self, *args: str) -> str:
        """
        Run a git command and return stdout.
        
        Why subprocess.run over os.system?
        - Captures output properly
        - Better error handling
        - No shell injection risks
        """
        try:
            result = subprocess.run(
                ['git', *args],
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8',
                errors='replace'  # Handle weird characters gracefully
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
        """
        Get staged changes only.
        
        Returns a StagedChanges object with:
        - List of changed files with line counts
        - The actual diff content
        """
        files = self._get_staged_files()
        diff = self._get_staged_diff()
        
        return StagedChanges(files=files, diff=diff)
    
    def _get_staged_files(self) -> list[FileChange]:
        """
        Parse 'git diff --staged --numstat' output.
        
        Only reads STAGED changes - respects what user chose to commit.
        """
        output = self._run_git('diff', '--staged', '--numstat')
        
        if not output.strip():
            return []
        
        files = []
        for line in output.strip().split('\n'):
            parts = line.split('\t')
            if len(parts) >= 3:
                # Binary files show '-' for additions/deletions
                additions = int(parts[0]) if parts[0] != '-' else 0
                deletions = int(parts[1]) if parts[1] != '-' else 0
                path = parts[2]
                
                files.append(FileChange(
                    path=path,
                    additions=additions,
                    deletions=deletions
                ))
        
        return files
    
    def _get_staged_diff(self) -> str:
        """
        Get the actual diff content for staged changes.
        """
        return self._run_git('diff', '--staged')


# Quick test when run directly
if __name__ == "__main__":
    try:
        analyzer = GitAnalyzer()
        changes = analyzer.get_staged_changes()
        
        if changes.is_empty:
            print("No staged changes")
        else:
            print(f"Staged: {changes.total_files} files")
            print(f"  +{changes.total_additions} -{changes.total_deletions} lines\n")
            
            for f in changes.files:
                print(f"  {f.path}: +{f.additions} -{f.deletions}")
                
    except GitError as e:
        print(f"Error: {e}")
