# git-scribe

[![CI](https://github.com/arcanesandip/git-scribe/actions/workflows/ci.yml/badge.svg)](https://github.com/arcanesandip/git-scribe/actions/workflows/ci.yml)

A zero-dependency, heuristic-driven CLI utility that auto-stages, auto-messages, commits, and pushes — for solo, private repos where you don't want to think about commit hygiene mid-flow.

Run `gcap`. It stages everything, figures out a reasonable conventional-commit type and scope from what changed, writes a categorized commit body, commits, and pushes. No prompts, no API keys, no network calls beyond git itself.

---

## Why

On solo projects and dotfiles, stopping to write a commit message is pure friction — and skipping it leads to a history full of `update`, `wip`, `asdf`. `git-scribe` removes the decision entirely:

- **Local only.** Standard library + git. No API keys, no telemetry, works offline.
- **Deterministic.** No LLM calls, no network latency, no surprises.
- **Built for one person.** No review gate, no team conventions to satisfy — just a clean, searchable ledger of your own history.

This is explicitly *not* built for shared or team repos — see [Scope & limitations](#scope--limitations).

---

## How it works

```
[Working tree]
     │
     ▼  git add -A
[State capture]      → git status / diff --cached / --name-status
     │
     ▼
[File classifier]    → splits changes into Added (+) / Modified (~) / Deleted (-)
     │
     ▼
[Intent heuristic]   → picks a conventional-commit type from diff + filename
     │
     ▼
[Scope extraction]   → derives scope from the changed file's parent directory
     │
     ▼
[Commit + push]      → git commit -m "<type>(<scope>): ..." && git push
```

**Intent rules** (first match wins):

| Condition | Type |
|---|---|
| Commit is deletions only | `refactor` |
| Diff content contains the word `fix`, `bug`, `hotfix`, or `patch` | `fix` |
| Top file is `.md` / `.txt` / `.rst` | `docs` |
| Top file is a config/dotfile (`.config`, `.zsh`, `.json`, `.yaml`, `.yml`, `.toml`) | `config` |
| Diff content contains the word `def`, `class`, or `function` | `feat` |
| None of the above | `chore` |

Keyword matching uses **word-boundary regex over actual added/removed diff lines only** — diff headers, hunk markers (`@@ ... @@`), and file-path metadata are excluded first, so a file literally named `bugfix_notes.py` or a word like "prefix"/"definitely" won't false-positive on `fix`/`def`.

> **Heuristic, not ground truth.** It's still text pattern-matching, not code understanding — a comment that genuinely contains the standalone word "fix" will still match. For a private ledger that's a cosmetic issue, not a correctness one. Treat the generated type as a good default you can always amend.

---

## Install

1. Save the script:

   ```bash
   mkdir -p ~/scripts
   # save git-scribe.py into ~/scripts/git-scribe.py
   chmod +x ~/scripts/git-scribe.py
   ```

2. Add the shell function to `~/.zshrc` (or `~/.bashrc`):

   ```bash
   # ==========================================
   # GITHUB AUTOMATION SHORTCUTS
   # ==========================================

   unalias gcap 2>/dev/null

   gcap() {
       # Local project script takes priority, then a scripts/ folder,
       # then your home scripts dir, then a plain fallback.
       if [[ -f "./git-scribe.py" ]]; then
           python3 ./git-scribe.py
       elif [[ -f "./scripts/git-scribe.py" ]]; then
           python3 ./scripts/git-scribe.py
       elif [[ -f "$HOME/scripts/git-scribe.py" ]]; then
           python3 "$HOME/scripts/git-scribe.py"
       else
           git add . && git commit -m "Auto-update: $(date +'%Y-%m-%d %H:%M:%S')" && git push
       fi
   }

   gcm() {
       if [[ -z "$1" ]]; then
           echo "Usage: gcm \"commit message\""
           return 1
       fi
       git add . && git commit -m "$1" && git push
   }
   ```

3. Reload:

   ```bash
   source ~/.zshrc
   ```

`gcap` checks, in order: a `git-scribe.py` in the current directory, then `./scripts/`, then `~/scripts/`, then falls back to a plain timestamped commit if the script isn't found anywhere. `gcm "message"` is the manual override for when you want to write your own message.

---

## Usage

```bash
cd your-project
# ... make changes ...
gcap
```

```
Scribed & pushed: feat(scripts): auto-update 3 file(s) [via gcap]
```

Example resulting commit:

```
commit a8f2c91
Author: you
Date:   Mon Jul 27 2026

    feat(scripts): auto-update 3 file(s) [via gcap]

    Added files:
    + scripts/new_module.py

    Modified files:
    ~ scripts/git-scribe.py

    Deleted files:
    - scripts/legacy_parser.py
```

Need a message you control instead? Use `gcm "your message here"`.

---

## Scope & limitations

Built and tuned for **private, single-person use**. Specifically, it does *not*:

- Show you a diff or ask for confirmation before committing — everything staged gets committed, every time.
- Guarantee correct commit types/scopes — it's pattern matching on text, not code analysis.
- Guard against secrets in the diff (`.env`, tokens, keys) — make sure your `.gitignore` covers anything sensitive before relying on `git add -A`.
- Handle merge conflicts, rebases, or a rejected push (diverged remote) — those still need manual `git pull`/`git rebase`.

None of that matters for a solo repo where you're the only reader of the history. If you ever point this at a shared/team repo, add a review step first.

---

## Testing

The pure logic (file classification, intent detection, scope extraction, commit body formatting) is covered by a small `pytest` suite in `tests/`. It doesn't touch git or the filesystem, so it runs anywhere:

```bash
pip install pytest pycodestyle
python -m pytest tests/ -v
python -m pycodestyle --max-line-length=79 git-scribe.py
```

Both run automatically on every push via GitHub Actions — see the badge above.

---

## Requirements

- Python 3.6+
- `git` on your `PATH`
- A remote already configured for `git push` to succeed

No third-party packages.
