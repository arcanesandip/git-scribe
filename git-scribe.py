#!/usr/bin/env python3
"""git-scribe (gcap): auto-stage, auto-message, commit, and push."""
import re
import subprocess
import sys

# Diff header/hunk lines to exclude when scanning for intent keywords, so
# we only look at actual added/removed content, not metadata like
# "+++ b/file.py" or "@@ -1,4 +1,6 @@".
_DIFF_HEADER_PREFIXES = ("diff --git", "index ", "+++", "---", "@@")

_FIX_PATTERN = re.compile(r"\b(fix|bug|hotfix|patch)\b", re.IGNORECASE)
_FEAT_PATTERN = re.compile(r"\b(def|class|function)\b")


def run(cmd):
    """Run a shell command (read-only git queries) and return stdout."""
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=True,
    )
    return result.stdout.strip()


def run_argv(cmd_list):
    """Run a command as an argv list (no shell) for mutating git calls.

    Returns (returncode, stdout, stderr).
    """
    result = subprocess.run(
        cmd_list,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def classify_files(status_output):
    """Split `git diff --name-status` output into added/modified/deleted."""
    added, modified, deleted = [], [], []
    for line in status_output.splitlines():
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        status_code, filepath = parts
        if status_code.startswith("A"):
            added.append(filepath)
        elif status_code.startswith("D"):
            deleted.append(filepath)
        else:
            modified.append(filepath)
    return added, modified, deleted


def diff_content_lines(diff_data):
    """Extract only real added/removed content lines from a unified diff.

    Strips out diff headers and hunk markers (e.g. "diff --git",
    "index ...", "+++", "---", "@@ ... @@") so keyword matching only
    ever looks at lines someone actually wrote or removed, not diff
    metadata or file paths.
    """
    content = []
    for line in diff_data.splitlines():
        if line.startswith(_DIFF_HEADER_PREFIXES):
            continue
        if line.startswith(("+", "-")):
            content.append(line[1:])
    return content


def detect_intent(diff_data, top_file, ext, is_deletion):
    """Heuristic conventional-commit type from diff content and filename.

    Keyword checks use word-boundary regex against actual diff content
    lines only (not headers/hunk markers), so "prefix" won't match
    "fix" and a filename mention won't leak into the diff scan. It's
    still a heuristic over text, not a semantic understanding of the
    change, so treat the result as a helpful default, not ground truth.
    """
    if is_deletion:
        return "refactor"

    content_text = "\n".join(diff_content_lines(diff_data))

    if _FIX_PATTERN.search(content_text):
        return "fix"
    if ext in ("md", "txt", "rst"):
        return "docs"
    if (".config" in top_file or ".zsh" in top_file
            or ext in ("json", "yaml", "yml", "toml")):
        return "config"
    if _FEAT_PATTERN.search(content_text):
        return "feat"
    return "chore"


def extract_scope(top_file, ext):
    """Derive a conventional-commit scope from the changed file's path."""
    if "/" in top_file:
        parts = top_file.split("/")
        return parts[-2] if len(parts) > 1 else parts[0]
    return ext if ext else "misc"


def build_body(added, modified, deleted):
    """Build a categorized commit body from added/modified/deleted lists."""
    parts = []
    if added:
        lines = "\n".join(f"+ {f}" for f in added)
        parts.append(f"Added files:\n{lines}")
    if modified:
        lines = "\n".join(f"~ {f}" for f in modified)
        parts.append(f"Modified files:\n{lines}")
    if deleted:
        lines = "\n".join(f"- {f}" for f in deleted)
        parts.append(f"Deleted files:\n{lines}")
    return "\n\n".join(parts)


def main():
    # 1. Ensure we are inside a git repository
    if run("git rev-parse --is-inside-work-tree") != "true":
        print("Error: Not a git repository.")
        sys.exit(1)

    # 2. Check for changes
    if not run("git status --porcelain"):
        print("No changes to commit.")
        sys.exit(0)

    # Stage everything automatically
    run("git add -A")
    diff_data = run("git diff --cached")
    status_output = run("git diff --cached --name-status")
    changed_files = run("git diff --cached --name-only").splitlines()
    file_count = len(changed_files)

    if not changed_files:
        print("Nothing staged.")
        sys.exit(0)

    top_file = changed_files[0]
    ext = top_file.split(".")[-1] if "." in top_file else ""

    added_files, modified_files, deleted_files = classify_files(
        status_output
    )
    is_deletion = (
        deleted_files and not added_files and not modified_files
    )

    intent = detect_intent(diff_data, top_file, ext, is_deletion)
    scope = extract_scope(top_file, ext)

    msg = f"{intent}({scope}): auto-update {file_count} file(s) [via gcap]"
    body = build_body(added_files, modified_files, deleted_files)

    # Commit as an argv list (no shell) so quotes/backticks/$ in file
    # paths or diff content can't break out of the command string.
    commit_code, commit_out, commit_err = run_argv(
        ["git", "commit", "-m", msg, "-m", body]
    )
    if commit_code != 0:
        print(f"Commit failed:\n{commit_err or commit_out}")
        sys.exit(1)

    # Check the real exit code / stderr, not a stdout substring guess.
    push_code, push_out, push_err = run_argv(["git", "push"])
    if push_code != 0:
        print(f"Scribed locally, but push failed:\n{push_err or push_out}")
        sys.exit(1)

    print(f"Scribed & Pushed: {msg}")


if __name__ == "__main__":
    main()
