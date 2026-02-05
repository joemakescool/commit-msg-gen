"""
Commit Message Generator

AI-powered commit message generation from staged git changes.
"""

__version__ = "1.0.0"

# Centralized commit types - single source of truth
# Used by: prompt_builder.py, llm_client.py (validation), cli.py (argparse)
COMMIT_TYPES = {
    'feat': 'A new feature or capability',
    'fix': 'A bug fix',
    'refactor': 'Code restructuring without behavior change',
    'chore': 'Maintenance tasks, dependencies, tooling',
    'docs': 'Documentation only changes',
    'test': 'Adding or updating tests',
    'style': 'Formatting, whitespace, no code change',
    'perf': 'Performance improvement',
    'ci': 'CI/CD configuration changes',
    'build': 'Build system or external dependency changes',
}

# List of type names for validation and argparse
COMMIT_TYPE_NAMES = list(COMMIT_TYPES.keys())

# Note on breaking changes: Use "feat!:" or "fix!:" (with !) for breaking changes
# Example: feat!(api): remove deprecated endpoints
