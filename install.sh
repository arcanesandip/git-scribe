#!/usr/bin/env bash
#
# install.sh — installs git-scribe (gcap) for the current user.
#
# What it does:
#   1. Checks for required tools (python3, git) and warns about the
#      optional AI step (Ollama) without failing if it's missing.
#   2. Copies git-scribe.py into ~/scripts/git-scribe.py
#   3. Adds the gcap()/gcm() shell functions to your shell rc file,
#      safely — running this script twice won't duplicate the block.
#
# Usage:
#   ./install.sh
#
set -euo pipefail

SCRIPT_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/git-scribe.py"
INSTALL_DIR="$HOME/scripts"
INSTALL_PATH="$INSTALL_DIR/git-scribe.py"

MARKER_START="# >>> git-scribe (gcap) >>>"
MARKER_END="# <<< git-scribe (gcap) <<<"

info()  { printf '  %s\n' "$1"; }
ok()    { printf '\033[32m✓\033[0m %s\n' "$1"; }
warn()  { printf '\033[33m!\033[0m %s\n' "$1"; }
err()   { printf '\033[31m✗\033[0m %s\n' "$1" >&2; }

echo "git-scribe installer"
echo "---------------------"

# --- 1. Required prerequisites ------------------------------------------

if ! command -v python3 >/dev/null 2>&1; then
    err "python3 not found on PATH. Install Python 3.6+ and re-run this script."
    exit 1
fi
ok "python3 found ($(python3 --version 2>&1))"

if ! command -v git >/dev/null 2>&1; then
    err "git not found on PATH. Install git and re-run this script."
    exit 1
fi
ok "git found ($(git --version))"

if [[ ! -f "$SCRIPT_SOURCE" ]]; then
    err "Couldn't find git-scribe.py next to this install script."
    err "Expected it at: $SCRIPT_SOURCE"
    exit 1
fi

# --- 2. Optional: Ollama for the AI-verification step -------------------

SELECTED_MODEL="qwen2.5-coder:1.5b"

if command -v ollama >/dev/null 2>&1; then
    ok "ollama found — AI-assisted commit descriptions available"

    if [[ -t 0 ]]; then
        echo ""
        echo "  Which Qwen2.5-Coder size should gcap use?"
        echo "  (larger = better descriptions, but uses more VRAM and"
        echo "   competes with whatever else needs your GPU per commit)"
        echo ""
        echo "    1) 1.5b  — recommended: fast, stays out of the way (~2GB)"
        echo "    2) 3b    — noticeably better, still light (~4GB)"
        echo "    3) 7b    — strong results, needs a real GPU (~8GB)"
        echo "    4) 14b   — best quality, workstation-grade GPU (~16GB+)"
        echo "    5) custom — type your own model tag"
        echo ""
        read -r -p "  Choice [1]: " model_choice
        case "${model_choice:-1}" in
            1) SELECTED_MODEL="qwen2.5-coder:1.5b" ;;
            2) SELECTED_MODEL="qwen2.5-coder:3b" ;;
            3) SELECTED_MODEL="qwen2.5-coder:7b" ;;
            4) SELECTED_MODEL="qwen2.5-coder:14b" ;;
            5)
                read -r -p "  Model tag (e.g. qwen2.5-coder:32b): " custom_model
                SELECTED_MODEL="${custom_model:-qwen2.5-coder:1.5b}"
                ;;
            *)
                warn "Unrecognized choice, using recommended default (1.5b)."
                SELECTED_MODEL="qwen2.5-coder:1.5b"
                ;;
        esac
        echo ""
    else
        info "Non-interactive install — using recommended default: $SELECTED_MODEL"
    fi

    ok "selected model: $SELECTED_MODEL"

    if ollama list 2>/dev/null | awk '{print $1}' \
            | grep -qx "$SELECTED_MODEL"; then
        ok "model '$SELECTED_MODEL' appears to be pulled"
    else
        warn "model '$SELECTED_MODEL' not found in 'ollama list'."
        if [[ -t 0 ]]; then
            read -r -p "  Pull it now? [Y/n]: " pull_now
            if [[ ! "$pull_now" =~ ^[Nn] ]]; then
                ollama pull "$SELECTED_MODEL" || \
                    warn "Pull failed — you can retry later with: ollama pull $SELECTED_MODEL"
            fi
        else
            warn "Pull it with: ollama pull $SELECTED_MODEL"
        fi
        warn "(gcap will still work without it — falls back to heuristics.)"
    fi
else
    warn "ollama not found — that's fine, gcap works without it."
    warn "It'll fall back to the deterministic heuristic result."
    warn "To enable AI-assisted descriptions later: https://ollama.com"
fi

# --- 3. Install the script ------------------------------------------------

mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_SOURCE" "$INSTALL_PATH"
chmod +x "$INSTALL_PATH"
ok "installed to $INSTALL_PATH"

# --- 4. Detect shell rc file ----------------------------------------------

CURRENT_SHELL="$(basename "${SHELL:-bash}")"
case "$CURRENT_SHELL" in
    zsh)  RC_FILE="$HOME/.zshrc" ;;
    bash) RC_FILE="$HOME/.bashrc" ;;
    *)
        warn "Unrecognized shell '$CURRENT_SHELL' — defaulting to ~/.bashrc"
        RC_FILE="$HOME/.bashrc"
        ;;
esac

touch "$RC_FILE"

# --- 5. Add the shell function block, idempotently -------------------------

if grep -qF "$MARKER_START" "$RC_FILE" 2>/dev/null; then
    ok "gcap/gcm functions already present in $RC_FILE — leaving as is"
    if [[ "$SELECTED_MODEL" != "qwen2.5-coder:1.5b" ]]; then
        info "Note: you picked '$SELECTED_MODEL' but an existing block is"
        info "already there — edit GCAP_MODEL in $RC_FILE by hand if needed."
    fi
else
    cat >> "$RC_FILE" <<EOF

$MARKER_START
unalias gcap 2>/dev/null

export GCAP_MODEL="\${GCAP_MODEL:-$SELECTED_MODEL}"

gcap() {
    # Local project script takes priority, then a scripts/ folder,
    # then your home scripts dir, then a plain fallback.
    if [[ -f "./git-scribe.py" ]]; then
        python3 ./git-scribe.py
    elif [[ -f "./scripts/git-scribe.py" ]]; then
        python3 ./scripts/git-scribe.py
    elif [[ -f "\$HOME/scripts/git-scribe.py" ]]; then
        python3 "\$HOME/scripts/git-scribe.py"
    else
        git add . && git commit -m "Auto-update: \$(date +'%Y-%m-%d %H:%M:%S')" && git push
    fi
}

gcm() {
    if [[ -z "\$1" ]]; then
        echo "Usage: gcm \"commit message\""
        return 1
    fi
    git add . && git commit -m "\$1" && git push
}
$MARKER_END
EOF
    ok "added gcap/gcm functions to $RC_FILE"
fi

echo "---------------------"
echo "Done. Run this to start using it in your current shell:"
echo ""
echo "  source $RC_FILE"
echo ""
echo "Then just: cd into a git repo, make changes, run 'gcap'."
