"""
Tests for CLI output formatting.

Shows sample output for each scenario. Run with:
    pytest tests/test_display.py -v
    pytest tests/test_display.py -v -s   # see actual terminal output
"""

import re

import pytest

from src.git.diff_processor import ProcessedDiff
from src.cli.main import _display_file_list, _display_message
from src.cli.utils import clean_commit_message
from src.output import success, dim, bold, info, CHECK

ANSI_RE = re.compile(r'\033\[[0-9;]*m')


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def strip_ansi():
    """Return a function that removes ANSI escape codes."""
    def _strip(text: str) -> str:
        return ANSI_RE.sub('', text)
    return _strip


@pytest.fixture
def print_sample(capsys):
    """Return a function that replays captured output for -s viewing."""
    def _print(out: str):
        with capsys.disabled():
            try:
                print(out)
            except UnicodeEncodeError:
                # Windows cp1252 can't encode Unicode symbols (─, ✓, etc.)
                cleaned = ANSI_RE.sub('', out)
                print(cleaned.encode('ascii', errors='replace').decode('ascii'))
    return _print


@pytest.fixture
def make_processed():
    """Return a factory that builds ProcessedDiff from a file list."""
    def _make(file_details, filtered=0):
        return ProcessedDiff(
            summary="",
            detailed_diff="",
            total_files=len(file_details) + filtered,
            included_files=len(file_details),
            filtered_files=filtered,
            file_details=file_details,
        )
    return _make


# ---------------------------------------------------------------------------
# File list display
# ---------------------------------------------------------------------------

class TestDisplayFileList:
    """Output from _display_file_list()."""

    def test_small_list_shows_all(self, capsys, make_processed):
        """3 files — every file is printed."""
        p = make_processed([
            ("src/utils/validator.py", 15, 3),
            ("src/utils/__init__.py", 1, 0),
            ("tests/test_validator.py", 22, 0),
        ])
        _display_file_list(p)
        out = capsys.readouterr().out

        assert "Staged changes:" in out
        assert "src/utils/validator.py (+15 -3)" in out
        assert "src/utils/__init__.py (+1 -0)" in out
        assert "tests/test_validator.py (+22 -0)" in out
        assert "..." not in out

    def test_large_list_collapses(self, capsys, make_processed):
        """12 files — first 8 shown, rest collapsed."""
        files = [(f"src/mod_{i}.py", 10 + i, i) for i in range(12)]
        p = make_processed(files)
        _display_file_list(p)
        out = capsys.readouterr().out

        # First 8 visible
        assert "src/mod_0.py" in out
        assert "src/mod_7.py" in out
        # 9th onward hidden
        assert "src/mod_8.py" not in out
        assert "... and 4 more files" in out

    def test_shows_filtered_count(self, capsys, make_processed):
        """Noise file count appears when files are filtered."""
        p = make_processed([("src/app.py", 5, 2)], filtered=3)
        _display_file_list(p)
        out = capsys.readouterr().out

        assert "3 noise files filtered" in out

    def test_hides_filtered_when_zero(self, capsys, make_processed):
        """No noise line when nothing was filtered."""
        p = make_processed([("src/app.py", 5, 2)], filtered=0)
        _display_file_list(p)
        out = capsys.readouterr().out

        assert "noise" not in out

    def test_empty_details_prints_nothing(self, capsys, make_processed):
        """No output for empty file list."""
        p = make_processed([])
        _display_file_list(p)
        out = capsys.readouterr().out

        assert out == ""


# ---------------------------------------------------------------------------
# Commit message display
# ---------------------------------------------------------------------------

class TestDisplayMessage:
    """Output from _display_message()."""

    def test_subject_with_body(self, capsys, strip_ansi):
        msg = (
            "feat(auth): add JWT token refresh\n"
            "\n"
            "- implement automatic refresh before expiry\n"
            "- store refresh token in httpOnly cookies"
        )
        _display_message(msg)
        out = strip_ansi(capsys.readouterr().out)

        assert "feat(auth): add JWT token refresh" in out
        assert "- implement automatic refresh before expiry" in out
        assert "- store refresh token in httpOnly cookies" in out

    def test_subject_only(self, capsys, strip_ansi):
        _display_message("fix(api): handle null response")
        out = strip_ansi(capsys.readouterr().out)

        assert "fix(api): handle null response" in out

    def test_has_horizontal_rules(self, capsys, strip_ansi):
        _display_message("chore: update dependencies")
        out = strip_ansi(capsys.readouterr().out)
        lines = [l for l in out.split("\n") if l.strip()]

        # First and last lines are rules
        assert all(c == "\u2500" for c in lines[0].strip())
        assert all(c == "\u2500" for c in lines[-1].strip())


# ---------------------------------------------------------------------------
# clean_commit_message — parametrized
# ---------------------------------------------------------------------------

class TestCleanCommitMessage:

    @pytest.mark.parametrize("raw, expected", [
        pytest.param(
            "Here's a commit message:\n\nfeat(cli): add verbose mode",
            "feat(cli): add verbose mode",
            id="strips-preamble",
        ),
        pytest.param(
            "```\nfix(api): handle timeout\n```",
            "fix(api): handle timeout",
            id="strips-backticks",
        ),
        pytest.param(
            "feat(auth): add login\n\n- add /login endpoint\n- validate credentials",
            "feat(auth): add login\n\n- add /login endpoint\n- validate credentials",
            id="preserves-body",
        ),
    ])
    def test_clean_message(self, raw, expected):
        assert clean_commit_message(raw) == expected

    def test_strips_trailing_diff(self):
        raw = (
            "refactor(db): extract query builder\n"
            "\n"
            "- new QueryBuilder class\n"
            "\n"
            "diff --git a/foo.py b/foo.py"
        )
        result = clean_commit_message(raw)
        assert "diff --git" not in result
        assert "refactor(db): extract query builder" in result
        assert "- new QueryBuilder class" in result


# ---------------------------------------------------------------------------
# Full console output — run with -s to see what users see
#   pytest tests/test_display.py::TestConsoleOutput -v -s
# ---------------------------------------------------------------------------

@pytest.fixture
def simulate_console(capsys, make_processed, strip_ansi, print_sample):
    """Return a function that reproduces the full cm console flow."""
    def _simulate(*, files, filtered, provider, message):
        processed = make_processed(files, filtered=filtered)

        # 1. File list
        _display_file_list(processed)

        # 2. Status line (mock)
        total = len(files) + filtered
        print(f"Analyzing {bold(str(total))} files using {info(provider)}... {success('done!')}")

        # 3. Commit message
        _display_message(message)

        # 4. Clipboard
        print(f"{success(CHECK)} Copied to clipboard!")

        # 5. Interactive prompt
        print(f"\n{dim('(e)dit, (r)egenerate, or Enter to accept: ')}")

        # Capture, display for -s, return for assertions
        out = capsys.readouterr().out
        print_sample(out)
        return strip_ansi(out)
    return _simulate


class TestConsoleOutput:
    """
    Full console mock — shows exactly what a user sees after running cm.

    Run:  pytest tests/test_display.py::TestConsoleOutput -v -s
    """

    def test_quick_bugfix(self, simulate_console):
        """cm output for a small 2-file bug fix."""
        out = simulate_console(
            files=[
                ("src/utils/validator.py", 15, 3),
                ("src/utils/__init__.py", 1, 0),
            ],
            filtered=0,
            provider="Ollama (mistral:7b)",
            message=(
                "fix(utils): add null check for email validation\n"
                "\n"
                "- return False for None email input\n"
                "- export validate_email from utils package"
            ),
        )

        assert "validator.py (+15 -3)" in out
        assert "Analyzing 2 files" in out
        assert "done!" in out
        assert "fix(utils): add null check" in out
        assert "Copied to clipboard!" in out
        assert "(e)dit, (r)egenerate" in out

    def test_feature_with_noise(self, simulate_console):
        """cm output for a 6-file feature with lock files filtered."""
        out = simulate_console(
            files=[
                ("src/api/auth_controller.py", 85, 12),
                ("src/services/auth_service.py", 120, 0),
                ("src/models/user.py", 25, 5),
                ("src/middleware/jwt.py", 45, 0),
                ("tests/test_auth.py", 90, 0),
                ("config/auth.yaml", 15, 0),
            ],
            filtered=2,
            provider="Claude (claude-sonnet-4-20250514)",
            message=(
                "feat(auth): add JWT authentication with login/logout\n"
                "\n"
                "- add login and logout endpoints to auth controller\n"
                "- implement JWT token generation and validation service\n"
                "- add password_hash and last_login fields to user model\n"
                "- create JWT middleware for protected routes"
            ),
        )

        assert "auth_controller.py (+85 -12)" in out
        assert "2 noise files filtered" in out
        assert "Analyzing 8 files" in out
        assert "feat(auth):" in out
        assert "- add login and logout" in out
        assert "Copied to clipboard!" in out

    def test_large_refactor_collapsed(self, simulate_console):
        """cm output for a 16-file refactor where the file list collapses."""
        out = simulate_console(
            files=[
                ("src/api/predictions_controller.py", 45, 120),
                ("src/api/teams_controller.py", 30, 85),
                ("src/api/games_controller.py", 25, 70),
                ("src/services/prediction_service.py", 180, 0),
                ("src/services/team_service.py", 95, 0),
                ("src/services/game_service.py", 85, 0),
                ("src/repositories/prediction_repo.py", 120, 0),
                ("src/repositories/team_repo.py", 80, 0),
                ("src/repositories/game_repo.py", 75, 0),
                ("src/models/prediction.py", 45, 15),
                ("src/models/team.py", 30, 10),
                ("src/models/game.py", 35, 12),
                ("src/utils/query_builder.py", 150, 0),
                ("src/utils/cache.py", 60, 0),
                ("tests/test_prediction_service.py", 200, 0),
                ("tests/test_team_service.py", 120, 0),
            ],
            filtered=2,
            provider="Ollama (llama3.1:8b)",
            message=(
                "refactor(api): extract service and repository layers\n"
                "\n"
                "- move business logic from controllers to service classes\n"
                "- create repository layer for database operations\n"
                "- add query builder utility for complex DataFrame operations\n"
                "- implement caching layer for frequently accessed data"
            ),
        )

        # First 8 files shown, rest collapsed
        assert "predictions_controller.py (+45 -120)" in out
        assert "team_repo.py (+80 -0)" in out
        assert "... and 8 more files" in out
        assert "2 noise files filtered" in out
        assert "Analyzing 18 files" in out
        assert "refactor(api):" in out
        assert "(e)dit, (r)egenerate" in out
