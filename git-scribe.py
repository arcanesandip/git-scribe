#!/usr/bin/env python3
"""git-scribe (gcap): heuristic pre-analysis + AI verification.

Also handles description generation and sync (commit + push).
"""
import json
import os
import re
import subprocess
import sys
import urllib.request

_DIFF_HEADER_PREFIXES = ("diff --git", "index ", "+++", "---", "@@")
_FIX_PATTERN = re.compile(r"\b(fix|bug|hotfix|patch)\b", re.IGNORECASE)
_FEAT_PATTERN = re.compile(r"\b(def|class|function)\b")

ALLOWED_TYPES = [
    "feat", "fix", "refactor", "docs", "chore", "style",
    "test", "perf", "build", "ci", "revert", "config",
]

# Model is configurable via GCAP_MODEL so people with more headroom can
# use a bigger, more accurate Qwen2.5-Coder variant. Default is 1.5b —
# picked deliberately, not as a ceiling: gcap runs on every commit, so
# it should stay light and not compete with the GPU for VRAM. See the
# README's "Choosing a model" section for a size/hardware guide.
MODEL = os.environ.get("GCAP_MODEL", "qwen2.5-coder:1.5b")
OLLAMA_URL = os.environ.get(
    "GCAP_OLLAMA_URL", "http://localhost:11434/api/chat"
)


def run(cmd):
    """Run a shell command (read-only git queries) and return stdout."""
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, shell=True,
    )
    return result.stdout.strip()


def run_argv(cmd_list):
    """Run a command as an argv list (no shell) for mutating git calls."""
    result = subprocess.run(
        cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
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
    """Extract only real added/removed content lines from a unified diff."""
    content = []
    for line in diff_data.splitlines():
        if line.startswith(_DIFF_HEADER_PREFIXES):
            continue
        if line.startswith(("+", "-")):
            content.append(line[1:])
    return content


def heuristic_detect_intent(diff_data, top_file, ext, is_deletion):
    """Python's first-pass heuristic intent detection."""
    if is_deletion:
        return "refactor"
    if ".github/workflows" in top_file:
        return "ci"

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


def heuristic_extract_scope(top_file, ext):
    """Python's first-pass scope extraction from file paths."""
    if "/" in top_file:
        parts = top_file.split("/")
        meaningful_parts = [p for p in parts if not p.startswith(".")]
        if meaningful_parts:
            return (meaningful_parts[-2] if len(meaningful_parts) > 1
                    else meaningful_parts[0])
        return parts[-2] if len(parts) > 1 else parts[0]
    return ext if ext else "misc"


def ai_verify_and_describe(diff_data, initial_type, initial_scope):
    """AI review loop: verify heuristic type/scope, write description."""
    prompt = f"""You are a Git commit validation engine.
Review the proposed heuristic type and scope against the git diff,
adjust them if necessary, and write a short imperative description.

Heuristic Proposed Type: {initial_type}
Heuristic Proposed Scope: {initial_scope}
Allowed Types: {", ".join(ALLOWED_TYPES)}

INSTRUCTIONS:
1. Confirm or correct the type/scope based on the diff.
2. Write a concise, imperative-tense short description (max 6-8
   words, no punctuation at the end) that summarizes ALL changed
   files in the diff, not just the first one.
3. Do not quote or repeat text found inside the diff (e.g.
   docstrings, comments) as the description — describe the change
   itself in your own words.
4. Output strictly in JSON with keys: "type", "scope", "description".

DIFF:
{diff_data}"""

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.1},
    }

    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            content = res_data.get("message", {}).get("content", "").strip()

            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip("`").strip()

            parsed = json.loads(content)

            final_type = parsed.get("type", initial_type)
            if final_type not in ALLOWED_TYPES:
                final_type = initial_type

            final_scope = parsed.get("scope", initial_scope).strip("/")
            description = parsed.get(
                "description", "update repository files"
            ).strip().strip('"').strip("'").strip().rstrip(".")

            return final_type, final_scope, description, None

    except Exception as exc:
        # Fall back gracefully to heuristics, but say why — a silent
        # fallback means you'd never know the AI step isn't working.
        return initial_type, initial_scope, "update repository files", exc


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
    if run("git rev-parse --is-inside-work-tree") != "true":
        print("Error: Not a git repository.")
        sys.exit(1)

    if not run("git status --porcelain"):
        print("No changes to commit.")
        sys.exit(0)

    run("git add -A")
    diff_data = run("git diff --cached")
    status_output = run("git diff --cached --name-status")
    changed_files = run("git diff --cached --name-only").splitlines()

    if not changed_files:
        print("Nothing staged.")
        sys.exit(0)

    top_file = changed_files[0]
    ext = top_file.split(".")[-1] if "." in top_file else ""

    added_files, modified_files, deleted_files = classify_files(
        status_output
    )
    is_deletion = deleted_files and not added_files and not modified_files

    initial_type = heuristic_detect_intent(
        diff_data, top_file, ext, is_deletion
    )
    initial_scope = heuristic_extract_scope(top_file, ext)

    print(f"Heuristics guessed -> Type: {initial_type} | "
          f"Scope: {initial_scope}")
    print(f"Running AI verification ({MODEL})...")

    final_type, final_scope, description, ai_error = ai_verify_and_describe(
        diff_data, initial_type, initial_scope
    )
    if ai_error is not None:
        print(f"AI verification unavailable ({ai_error}); "
              f"using heuristic result instead.")

    msg = f"{final_type}({final_scope}): {description}"
    body = build_body(added_files, modified_files, deleted_files)

    commit_code, commit_out, commit_err = run_argv(
        ["git", "commit", "-m", msg, "-m", body]
    )
    if commit_code != 0:
        print(f"Commit failed:\n{commit_err or commit_out}")
        sys.exit(1)

    push_code, push_out, push_err = run_argv(["git", "push"])
    if push_code != 0:
        print(f"Scribed locally, but push failed:\n{push_err or push_out}")
        sys.exit(1)

    print(f"Scribed & Pushed: {msg}")


if __name__ == "__main__":
    main()
