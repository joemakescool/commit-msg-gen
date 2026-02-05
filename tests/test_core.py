"""
Unit tests for core modules: DiffProcessor, PromptBuilder, Config, clean_commit_message.

Run with:
    pytest tests/test_core.py -v
"""

import json

import pytest

from src.cli.utils import clean_commit_message
from src.config import Config, ConfigManager
from src.git.analyzer import FileChange, StagedChanges
from src.git.diff_processor import DiffProcessor, ProcessedDiff, ProcessorConfig, Priority
from src.prompts.builder import PromptBuilder, PromptConfig


# ---------------------------------------------------------------------------
# DiffProcessor — file classification
# ---------------------------------------------------------------------------

class TestDiffProcessorClassify:
    """DiffProcessor._get_priority() file classification."""

    @pytest.fixture
    def processor(self):
        return DiffProcessor()

    @pytest.mark.parametrize("path, expected", [
        ("src/cli/main.py", Priority.SOURCE),
        ("app/models/user.rb", Priority.SOURCE),
        ("lib/utils.ts", Priority.SOURCE),
        ("index.js", Priority.SOURCE),
    ])
    def test_source_files(self, processor, path, expected):
        assert processor._get_priority(path) == expected

    @pytest.mark.parametrize("path", [
        "package-lock.json",
        "yarn.lock",
        "poetry.lock",
        "Cargo.lock",
        "Gemfile.lock",
        "dist/bundle.js",
        "build/output.js",
        "node_modules/pkg/index.js",
        ".min.js",
        "__pycache__/mod.pyc",
    ])
    def test_noise_files(self, processor, path):
        assert processor._get_priority(path) == Priority.NOISE

    @pytest.mark.parametrize("path", [
        "tests/test_main.py",
        "spec/models/user_spec.rb",
        "__tests__/App.test.js",
        "src/utils.test.ts",
        "src/utils.spec.ts",
        "UserTest.java",
    ])
    def test_test_files(self, processor, path):
        assert processor._get_priority(path) == Priority.TEST

    @pytest.mark.parametrize("path", [
        "config.json",
        "settings.yaml",
        "pyproject.toml",
        "app.config.js",
        "Dockerfile",
        "docker-compose.yml",
        "Makefile",
    ])
    def test_config_files(self, processor, path):
        assert processor._get_priority(path) == Priority.CONFIG

    @pytest.mark.parametrize("path", [
        "README.md",
        "CHANGELOG.rst",
        "docs/guide.md",
        "LICENSE",
        "notes.txt",
    ])
    def test_docs_files(self, processor, path):
        assert processor._get_priority(path) == Priority.DOCS


# ---------------------------------------------------------------------------
# DiffProcessor — processing
# ---------------------------------------------------------------------------

class TestDiffProcessorProcess:
    """DiffProcessor.process() end-to-end."""

    def _make_changes(self, file_paths, diff=""):
        files = [FileChange(path=p, additions=10, deletions=2) for p in file_paths]
        return StagedChanges(files=files, diff=diff)

    def test_filters_noise_files(self):
        changes = self._make_changes([
            "src/app.py",
            "package-lock.json",
            "yarn.lock",
        ])
        result = DiffProcessor().process(changes)

        assert result.total_files == 3
        assert result.filtered_files == 2
        assert "package-lock" not in result.summary
        assert "src/app.py" in result.summary

    def test_groups_by_priority(self):
        changes = self._make_changes([
            "tests/test_app.py",
            "src/app.py",
            "README.md",
        ])
        result = DiffProcessor().process(changes)
        lines = result.summary.split('\n')

        # Source should come before Test, which comes before Docs
        source_idx = next(i for i, l in enumerate(lines) if "Source" in l)
        test_idx = next(i for i, l in enumerate(lines) if "Tests" in l)
        docs_idx = next(i for i, l in enumerate(lines) if "Docs" in l)
        assert source_idx < test_idx < docs_idx

    def test_empty_diff_returns_empty_detailed(self):
        changes = self._make_changes(["src/app.py"], diff="")
        result = DiffProcessor().process(changes)
        assert result.detailed_diff == ""
        assert result.truncated is False

    def test_truncation_with_token_limit(self):
        # Create a diff large enough to exceed a small token limit
        big_diff = (
            "diff --git a/src/big.py b/src/big.py\n"
            + "+" * 5000 + "\n"
        )
        changes = self._make_changes(["src/big.py"], diff=big_diff)
        config = ProcessorConfig(max_tokens=100)
        result = DiffProcessor(config=config).process(changes)
        assert result.truncated is True

    def test_file_details_populated(self):
        changes = self._make_changes(["src/a.py", "src/b.py"])
        result = DiffProcessor().process(changes)
        assert len(result.file_details) == 2
        assert result.file_details[0][0] in ("src/a.py", "src/b.py")


# ---------------------------------------------------------------------------
# DiffProcessor — diff splitting
# ---------------------------------------------------------------------------

class TestDiffSplitByFile:

    def test_splits_multi_file_diff(self):
        diff = (
            "diff --git a/src/foo.py b/src/foo.py\n"
            "+added line in foo\n"
            "diff --git a/src/bar.py b/src/bar.py\n"
            "+added line in bar\n"
        )
        processor = DiffProcessor()
        result = processor._split_diff_by_file(diff)

        assert "src/foo.py" in result
        assert "src/bar.py" in result
        assert "added line in foo" in result["src/foo.py"]
        assert "added line in bar" in result["src/bar.py"]

    def test_single_file_diff(self):
        diff = (
            "diff --git a/src/only.py b/src/only.py\n"
            "+single file change\n"
        )
        processor = DiffProcessor()
        result = processor._split_diff_by_file(diff)

        assert len(result) == 1
        assert "src/only.py" in result


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------

class TestPromptBuilder:

    @pytest.fixture
    def builder(self):
        return PromptBuilder()

    @pytest.fixture
    def diff(self):
        return ProcessedDiff(
            summary="FILES CHANGED:\nsrc/app.py (+10 -2)",
            detailed_diff="+added line",
            total_files=1,
            included_files=1,
            filtered_files=0,
        )

    def test_build_returns_string(self, builder, diff):
        result = builder.build(diff)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_diff_content(self, builder, diff):
        result = builder.build(diff)
        assert "src/app.py" in result
        assert "+added line" in result

    def test_contains_role_section(self, builder, diff):
        result = builder.build(diff)
        assert "expert at writing git commit messages" in result

    def test_hint_included_when_provided(self, builder, diff):
        config = PromptConfig(hint="fixing the login bug")
        result = builder.build(diff, config)
        assert "fixing the login bug" in result

    def test_hint_excluded_when_none(self, builder, diff):
        config = PromptConfig(hint=None)
        result = builder.build(diff, config)
        assert "<context>" not in result

    def test_forced_type_in_prompt(self, builder, diff):
        config = PromptConfig(forced_type="fix")
        result = builder.build(diff, config)
        assert "Use type 'fix'" in result

    def test_simple_style_no_type_prefix(self, builder, diff):
        config = PromptConfig(style="simple")
        result = builder.build(diff, config)
        assert "without type prefixes" in result

    def test_multi_option_instructions(self, builder, diff):
        config = PromptConfig(num_options=3)
        result = builder.build(diff, config)
        assert "[Option 1]" in result
        assert "[Option 2]" in result
        assert "[Option 3]" in result

    def test_no_body_instruction(self, builder, diff):
        config = PromptConfig(include_body=False)
        result = builder.build(diff, config)
        assert "Do NOT include a body" in result

    def test_truncated_diff_note(self, builder):
        diff = ProcessedDiff(
            summary="FILES CHANGED:\nsrc/app.py (+10 -2)",
            detailed_diff="+added",
            total_files=1,
            truncated=True,
        )
        result = builder.build(diff)
        assert "truncated due to size" in result


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestConfig:

    def test_defaults(self):
        config = Config()
        assert config.provider == "auto"
        assert config.style == "conventional"
        assert config.include_body is True
        assert config.max_subject_length == 72

    def test_to_dict_excludes_none(self):
        config = Config()
        d = config.to_dict()
        assert "model" not in d
        assert "provider" in d

    def test_from_dict_ignores_unknown_keys(self):
        config = Config.from_dict({"provider": "claude", "unknown_key": "value"})
        assert config.provider == "claude"
        assert not hasattr(config, "unknown_key")

    def test_validate_invalid_provider(self):
        config = Config(provider="gpt4")
        warnings = config.validate()
        assert len(warnings) == 1
        assert config.provider == "auto"  # reset to default

    def test_validate_invalid_style(self):
        config = Config(style="fancy")
        warnings = config.validate()
        assert len(warnings) == 1
        assert config.style == "conventional"

    def test_validate_invalid_max_subject_length(self):
        config = Config(max_subject_length=-1)
        warnings = config.validate()
        assert any("max_subject_length" in w for w in warnings)
        assert config.max_subject_length == 72

    def test_validate_valid_config_no_warnings(self):
        config = Config()
        warnings = config.validate()
        assert warnings == []

    def test_from_dict_triggers_validation(self, capsys):
        Config.from_dict({"provider": "invalid"})
        err = capsys.readouterr().err
        assert "Config warning" in err


class TestConfigManager:

    def test_load_returns_defaults_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")
        manager = ConfigManager()
        config = manager.load()
        assert config.provider == "auto"
        assert config.style == "conventional"

    def test_load_reads_local_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / ".cmrc"
        config_file.write_text(json.dumps({"provider": "claude", "style": "simple"}))

        manager = ConfigManager()
        config = manager.load()
        assert config.provider == "claude"
        assert config.style == "simple"

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        # Also patch Path.home for Windows
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        manager = ConfigManager()
        original = Config(provider="ollama", style="detailed")
        manager.save(original, global_config=True)

        manager2 = ConfigManager()
        loaded = manager2.load()
        assert loaded.provider == "ollama"
        assert loaded.style == "detailed"

    def test_malformed_json_returns_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / ".cmrc"
        config_file.write_text("not valid json {{{")

        manager = ConfigManager()
        config = manager.load()
        assert config.provider == "auto"  # falls back to defaults


# ---------------------------------------------------------------------------
# clean_commit_message — additional edge cases
# ---------------------------------------------------------------------------

class TestCleanCommitMessageEdgeCases:

    def test_strips_llm_preamble(self):
        raw = "Sure! Here's a commit message:\n\nfeat(cli): add verbose flag"
        assert clean_commit_message(raw) == "feat(cli): add verbose flag"

    def test_strips_triple_backticks(self):
        raw = "```\nfix(api): handle timeout\n```"
        assert clean_commit_message(raw) == "fix(api): handle timeout"

    def test_preserves_body_bullets(self):
        raw = "feat(auth): add login\n\n- add endpoint\n- validate creds"
        assert clean_commit_message(raw) == raw

    def test_strips_trailing_diff_block(self):
        raw = (
            "refactor(db): extract builder\n\n"
            "- new class\n\n"
            "diff --git a/foo.py b/foo.py\n"
            "+some code"
        )
        result = clean_commit_message(raw)
        assert "diff --git" not in result
        assert "refactor(db): extract builder" in result

    def test_strips_trailing_code_block(self):
        raw = "fix(cli): escape args\n\n- fix quoting\n\n```python\ncode here\n```"
        result = clean_commit_message(raw)
        assert "```" not in result

    def test_handles_only_subject(self):
        raw = "chore: bump version"
        assert clean_commit_message(raw) == "chore: bump version"

    def test_handles_type_with_bang(self):
        raw = "feat!(api): remove deprecated endpoints"
        # The ! should still match via the ( or : in the regex
        result = clean_commit_message(raw)
        assert "feat!" in result

    def test_handles_type_with_scope(self):
        raw = "fix(config): correct default value"
        assert clean_commit_message(raw) == raw

    def test_whitespace_only_preamble(self):
        raw = "   \n\nfeat(cli): add flag"
        assert clean_commit_message(raw) == "feat(cli): add flag"


# ---------------------------------------------------------------------------
# FileChange dataclass
# ---------------------------------------------------------------------------

class TestFileChange:

    def test_total_changes(self):
        fc = FileChange(path="src/app.py", additions=10, deletions=3)
        assert fc.total_changes == 13

    def test_directory_src_layout(self):
        fc = FileChange(path="src/cli/main.py", additions=1, deletions=0)
        assert fc.directory == "cli"

    def test_directory_top_level(self):
        fc = FileChange(path="README.md", additions=1, deletions=0)
        assert fc.directory == "README.md"

    def test_directory_tests(self):
        fc = FileChange(path="tests/test_main.py", additions=1, deletions=0)
        assert fc.directory == "tests"


# ---------------------------------------------------------------------------
# ProcessedDiff
# ---------------------------------------------------------------------------

class TestProcessedDiff:

    def test_estimated_tokens(self):
        diff = ProcessedDiff(
            summary="a" * 100,
            detailed_diff="b" * 300,
            total_files=1,
        )
        assert diff.estimated_tokens == 100  # (100 + 300) // 4
