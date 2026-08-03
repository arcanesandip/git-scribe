# git-scribe

[![CI](https://github.com/arcanesandip/git-scribe/actions/workflows/ci.yml/badge.svg)](https://github.com/arcanesandip/git-scribe/actions/workflows/ci.yml)

Auto-stages, writes, commits, and pushes your git changes. Free, local, no accounts, no cloud API — including the optional AI step.

Run `gcap`. No prompts, no interruptions.

---

## Why

Stopping to write a commit message breaks flow, and skipping it leaves a history full of `update`, `wip`, `asdf`. `git-scribe` removes the decision:

- A word-boundary heuristic picks a type/scope. An optional local LLM can review and refine it.
- If the AI step isn't available, you still get a correct commit — never a blocked one.
- Built for solo use — no review gate, no team conventions. Not intended for shared repos; see [Scope & limitations](#scope--limitations).

---

## How it works

```
[Working tree]
     │
     ▼  git add -A
[State capture]        → git status / diff --cached / --name-status
     │
     ▼
[File classifier]      → Added (+) / Modified (~) / Deleted (-)
     │
     ▼
[Heuristic pre-pass]   → word-boundary rules → first-guess type + scope
     │
     ▼
[AI verification]      → optional, local — reviews/corrects the guess, writes a description
     │                     falls back to the heuristic result if unavailable
     ▼
[Commit + push]        → git commit -m "<type>(<scope>): <description>" && git push
```

### Heuristic rules (first match wins)

| Condition | Type |
|---|---|
| Commit is deletions only | `refactor` |
| Top file is under `.github/workflows/` | `ci` |
| Diff content contains `fix`, `bug`, `hotfix`, or `patch` | `fix` |
| Top file is `.md` / `.txt` / `.rst` | `docs` |
| Top file is a config/dotfile (`.config`, `.zsh`, `.json`, `.yaml`, `.yml`, `.toml`) | `config` |
| Diff content contains `def`, `class`, or `function` | `feat` |
| None of the above | `chore` |

Matching uses word-boundary regex over actual added/removed diff lines only — headers, hunk markers, and file paths are excluded, so `bugfix_notes.py` or "prefix" won't false-positive on `fix`/`def`. Still pattern-matching, not code understanding — treat the result as a good default you can amend.

### AI-assisted verification (optional)

Runs a second pass through a local LLM via [Ollama](https://ollama.com). It reviews the heuristic's guess, can correct type/scope, and writes the description. If Ollama isn't running or the model isn't pulled, `gcap` prints why and falls back to the heuristic — no hang, no failure.

**Default model: `qwen2.5-coder:1.5b`.** Deliberate, not a ceiling — `gcap` runs on every commit, so it stays light rather than competing with your GPU for VRAM.

Override with an environment variable:

```bash
export GCAP_MODEL="qwen2.5-coder:3b"   # or 7b, 14b, 32b
export GCAP_OLLAMA_URL="http://your-host:11434/api/chat"   # point at a different host
```

| Model | Approx. VRAM | Good fit if... |
|---|---|---|
| `1.5b` (default) | ~2 GB | Background use, integrated graphics, low VRAM |
| `3b` | ~4 GB | Mid-range GPU, want noticeably better summaries |
| `7b` | ~8 GB | Dedicated 8GB+ GPU, don't mind heavier use per commit |
| `14b`+ | 16 GB+ | Workstation GPU, not a shared laptop |

Bigger models summarize multi-file diffs more completely and are less prone to echoing unrelated text — a real capability gap tied to size, not the prompt.

---

## Install

### Option A: install script

```bash
git clone https://github.com/arcanesandip/git-scribe.git
cd git-scribe
./install.sh
```

Checks for `python3`/`git`, lets you pick a model size if Ollama is installed (1.5b recommended, just press Enter), offers to pull it, installs the script to `~/scripts/git-scribe.py`, and adds `gcap`/`gcm` to your shell rc file idempotently.

```bash
source ~/.zshrc   # or ~/.bashrc
```

### Option B: manual

1. ```bash
   mkdir -p ~/scripts
   # save git-scribe.py into ~/scripts/git-scribe.py
   chmod +x ~/scripts/git-scribe.py
   ```

2. Add to `~/.zshrc` (or `~/.bashrc`):
   ```bash
   unalias gcap 2>/dev/null

   gcap() {
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

3. `source ~/.zshrc`

`gcap` checks current dir → `./scripts/` → `~/scripts/` → falls back to a timestamped commit if the script isn't found. `gcm "message"` writes your own message manually.

---

## Usage

```bash
cd your-project
# ... make changes ...
gcap
```

```
Heuristics guessed -> Type: feat | Scope: scripts
Running AI verification (qwen2.5-coder:1.5b)...
Scribed & pushed: feat(scripts): add retry logic to push step
```

If the AI step isn't available:

```
Running AI verification (qwen2.5-coder:1.5b)...
AI verification unavailable ([Errno 111] Connection refused); using heuristic result instead.
Scribed & pushed: feat(scripts): auto-update 3 file(s) [via gcap]
```

---

## Scope & limitations

Built for **private, single-person use**. It does *not*:

- Show a diff or ask for confirmation — everything staged gets committed.
- Guarantee correct types/scopes/descriptions — heuristics are pattern matching, and the AI step can occasionally misdescribe a change.
- Guard against secrets in the diff — make sure `.gitignore` covers `.env`/tokens/keys before relying on `git add -A`.
- Handle merge conflicts, rebases, or a rejected push — those need manual `git pull`/`git rebase`.

Fine for a solo repo where you're the only reader. Add a review step first if used on a shared repo.

---

## Testing

```bash
pip install pytest pycodestyle
python -m pytest tests/ -v
python -m pycodestyle --max-line-length=79 git-scribe.py
```

Runs automatically on every push via GitHub Actions.

---

## Releases

- **[v1.0.0](https://github.com/arcanesandip/git-scribe/releases/tag/v1.0.0)** — fully deterministic, heuristic-only, zero network calls.
- **`main`** — adds the optional local AI-verification layer; falls back to the same heuristics if unavailable.

---

## Requirements

- Python 3.6+, `git` on `PATH`, a configured remote for `git push`
- *(Optional)* [Ollama](https://ollama.com) for AI-assisted descriptions

No third-party Python packages.

---

## License

MIT — see [LICENSE](LICENSE).
