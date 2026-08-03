"""Tests for git-scribe's pure logic and AI-fallback behavior.

These run anywhere with no repo, no filesystem writes, and no real
Ollama server required — the AI tests deliberately point at an
unreachable host so they exercise the fallback path fast and offline,
which is exactly what happens on CI runners (no Ollama installed).
"""
import importlib.util
import pathlib
import sys

_SCRIPT_PATH = pathlib.Path(__file__).resolve().parent.parent / "git-scribe.py"
_spec = importlib.util.spec_from_file_location("git_scribe", _SCRIPT_PATH)
git_scribe = importlib.util.module_from_spec(_spec)
sys.modules["git_scribe"] = git_scribe
_spec.loader.exec_module(git_scribe)


# ---- classify_files ----------------------------------------------------

def test_classify_files_splits_added_modified_deleted():
    status = "A\tnew_file.py\nM\tchanged_file.py\nD\told_file.py"
    added, modified, deleted = git_scribe.classify_files(status)
    assert added == ["new_file.py"]
    assert modified == ["changed_file.py"]
    assert deleted == ["old_file.py"]


def test_classify_files_handles_empty_input():
    added, modified, deleted = git_scribe.classify_files("")
    assert added == modified == deleted == []


def test_classify_files_ignores_blank_lines():
    status = "A\tfile_one.py\n\nM\tfile_two.py"
    added, modified, deleted = git_scribe.classify_files(status)
    assert added == ["file_one.py"]
    assert modified == ["file_two.py"]


def test_classify_files_renames_count_as_modified():
    status = "R100\told.py\tnew.py"
    added, modified, deleted = git_scribe.classify_files(status)
    assert modified == ["old.py\tnew.py"]


# ---- diff_content_lines --------------------------------------------------

def test_diff_content_lines_strips_headers_and_hunks():
    diff_data = (
        "diff --git a/app.py b/app.py\n"
        "index abc123..def456 100644\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,2 +1,3 @@\n"
        "+added line\n"
        "-removed line\n"
    )
    lines = git_scribe.diff_content_lines(diff_data)
    assert lines == ["added line", "removed line"]


def test_diff_content_lines_empty_diff():
    assert git_scribe.diff_content_lines("") == []


# ---- heuristic_detect_intent ---------------------------------------------

def test_detect_intent_deletion_only_is_refactor():
    intent = git_scribe.heuristic_detect_intent(
        diff_data="- removed_line()", top_file="old.py",
        ext="py", is_deletion=True,
    )
    assert intent == "refactor"


def test_detect_intent_workflow_file_is_ci():
    intent = git_scribe.heuristic_detect_intent(
        diff_data="+ name: CI", top_file=".github/workflows/ci.yml",
        ext="yml", is_deletion=False,
    )
    assert intent == "ci"


def test_detect_intent_fix_keyword():
    intent = git_scribe.heuristic_detect_intent(
        diff_data="+ fix null pointer bug", top_file="app.py",
        ext="py", is_deletion=False,
    )
    assert intent == "fix"


def test_detect_intent_docs_extension():
    intent = git_scribe.heuristic_detect_intent(
        diff_data="+ updated notes", top_file="NOTES.md",
        ext="md", is_deletion=False,
    )
    assert intent == "docs"


def test_detect_intent_config_extension():
    intent = git_scribe.heuristic_detect_intent(
        diff_data="+ key: value", top_file="settings.yaml",
        ext="yaml", is_deletion=False,
    )
    assert intent == "config"


def test_detect_intent_feat_keyword():
    intent = git_scribe.heuristic_detect_intent(
        diff_data="+ def new_feature():", top_file="app.py",
        ext="py", is_deletion=False,
    )
    assert intent == "feat"


def test_detect_intent_default_is_chore():
    intent = git_scribe.heuristic_detect_intent(
        diff_data="+ minor tweak", top_file="app.py",
        ext="py", is_deletion=False,
    )
    assert intent == "chore"


def test_detect_intent_does_not_false_positive_on_substring():
    intent = git_scribe.heuristic_detect_intent(
        diff_data="+ added a prefix helper function",
        top_file="utils.py", ext="py", is_deletion=False,
    )
    assert intent != "fix"


def test_detect_intent_ignores_diff_headers():
    diff_data = (
        "diff --git a/bugfix_notes.py b/bugfix_notes.py\n"
        "index abc123..def456 100644\n"
        "--- a/bugfix_notes.py\n"
        "+++ b/bugfix_notes.py\n"
        "@@ -1,2 +1,3 @@\n"
        "+added a helpful comment\n"
    )
    intent = git_scribe.heuristic_detect_intent(
        diff_data=diff_data, top_file="bugfix_notes.py",
        ext="py", is_deletion=False,
    )
    assert intent == "chore"


def test_detect_intent_fix_still_matches_real_word():
    intent = git_scribe.heuristic_detect_intent(
        diff_data="+ this line has a bug in the logic",
        top_file="app.py", ext="py", is_deletion=False,
    )
    assert intent == "fix"


def test_detect_intent_feat_ignores_word_without_boundary():
    intent = git_scribe.heuristic_detect_intent(
        diff_data="+ this is definitely a small tweak",
        top_file="app.py", ext="py", is_deletion=False,
    )
    assert intent == "chore"


# ---- heuristic_extract_scope ----------------------------------------------

def test_extract_scope_uses_parent_directory():
    scope = git_scribe.heuristic_extract_scope("src/auth/login.py", "py")
    assert scope == "auth"


def test_extract_scope_falls_back_to_extension():
    scope = git_scribe.heuristic_extract_scope("script.py", "py")
    assert scope == "py"


def test_extract_scope_falls_back_to_misc_when_no_extension():
    scope = git_scribe.heuristic_extract_scope("Makefile", "")
    assert scope == "misc"


def test_extract_scope_skips_dotfile_path_segments():
    scope = git_scribe.heuristic_extract_scope(
        ".github/workflows/ci.yml", "yml"
    )
    assert scope == "workflows"


# ---- build_body -----------------------------------------------------------

def test_build_body_includes_all_categories():
    body = git_scribe.build_body(
        added=["new.py"], modified=["changed.py"], deleted=["old.py"],
    )
    assert "Added files:\n+ new.py" in body
    assert "Modified files:\n~ changed.py" in body
    assert "Deleted files:\n- old.py" in body


def test_build_body_omits_empty_categories():
    body = git_scribe.build_body(added=["new.py"], modified=[], deleted=[])
    assert "Added files:" in body
    assert "Modified files:" not in body
    assert "Deleted files:" not in body


def test_build_body_empty_when_nothing_changed():
    assert git_scribe.build_body([], [], []) == ""


# ---- ai_verify_and_describe (fallback path only) --------------------------
#
# No real Ollama server is available on CI runners, so these tests only
# verify the graceful-fallback contract: when the AI step can't be
# reached, gcap must still return a usable (type, scope, description)
# tuple plus a non-None error, never raise, and never hang.

def test_ai_verify_falls_back_when_unreachable(monkeypatch):
    monkeypatch.setattr(
        git_scribe, "OLLAMA_URL", "http://127.0.0.1:1/api/chat"
    )
    final_type, final_scope, description, error = (
        git_scribe.ai_verify_and_describe(
            diff_data="+ def foo(): pass",
            initial_type="feat",
            initial_scope="app",
        )
    )
    assert final_type == "feat"
    assert final_scope == "app"
    assert description == "update repository files"
    assert error is not None


def test_ai_verify_fallback_does_not_raise(monkeypatch):
    monkeypatch.setattr(
        git_scribe, "OLLAMA_URL", "http://127.0.0.1:1/api/chat"
    )
    # Should return cleanly, not raise, even though the request fails.
    result = git_scribe.ai_verify_and_describe(
        diff_data="", initial_type="chore", initial_scope="misc",
    )
    assert len(result) == 4
