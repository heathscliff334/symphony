# symphony: instructions for AI agents

symphony is a CLI that fans tasks out to other agent CLIs (claude, codex, agy, mcode, cmd, opencode), each in its own git worktree, and reports every task's outcome. If the user asked you to install it, follow the steps below.

## Install

Requirements: macOS or Linux, `python3` (3.9 or newer), `git`, and `make`. No packages to install.

1. Work from this folder (the one containing `symphony.py` and this file).
2. Run `make install`. It symlinks `~/.local/bin/symphony` to `symphony.py`. It needs no sudo; do not use sudo.
3. Check that `~/.local/bin` is on `PATH`: `echo "$PATH" | tr ':' '\n' | grep -x "$HOME/.local/bin"`. If it prints nothing, tell the user and ask before editing their shell profile (`~/.zshrc` or `~/.bashrc`) to add `export PATH="$HOME/.local/bin:$PATH"`.
4. Verify from a different folder (no real agent needed):

```bash
cd /tmp && T=$(mktemp -d) && mkdir $T/w
printf '#!/bin/sh\necho '"'"'SYMPHONY_RESULT {"outcome":"succeeded","summary":"ok"}'"'"'\n' > $T/fake.sh && chmod +x $T/fake.sh
SYMPHONY_HOME=$T/home SYMPHONY_FAKE_BIN=$T/fake.sh sh -c '
  symphony run new check >/dev/null &&
  symphony start --harness fake --no-worktree --cwd '"$T"'/w --spec x >/dev/null &&
  symphony wait --timeout 20'
```

Success means one line ending in `succeeded ok` and exit code 0. Report the actual output to the user. If it fails, report the error text and stop; do not guess a fix.

## Install the skill for agents

`symphony install` links the skill into Claude Code (`~/.claude/skills`), the shared agents folder (`~/.agents/skills`, used by Codex) and Antigravity (`~/.gemini/config/skills`, used by the Antigravity app and agy). It is safe to repeat and refuses to overwrite anything that is not this skill.

- One agent only: `symphony install --agent claude` (or `agents`, `antigravity`).
- Any other agent: find where it keeps skills, then `symphony install --dir <that skills folder>`. Do not guess the folder; check the agent's own docs or config first.
- Remove: `symphony uninstall` takes the same flags and removes only links that point at this skill.

Restart the agent's session afterwards; skill lists load at session start.

## After install

Tell the user which of the six harnesses are installed (`command -v claude codex agy mcode cmd opencode`). Do not run real agents to "test" unless the user asks: each run uses their accounts and quota. When they do, use a throwaway git repo and the quick test in `README.md`, if present, or this:

```bash
symphony run new "smoke"
a=$(symphony start --harness claude --spec "Create hello.txt containing: hi")
symphony wait; symphony result "$a"
```

Known status (from `PHASE0_RESULTS.md`): claude, codex, agy, mcode and opencode passed the headless test; `cmd` did not (it reported success without creating the file). `symphony guide` prints `GUIDE.md`, which may not exist yet.

## Rules

- Use `--yolo` only if the user asks. It lets a worker run any command inside its worktree.
- A task is `failed` if the worker did not end with a `SYMPHONY_RESULT {...}` line, even when the work is fine. Check `symphony result <task>` before retrying.
- Merge `symphony/<task>` branches yourself, one at a time, after reading each result. Never merge unreviewed.
- Data lives in `~/.symphony` (override with `SYMPHONY_HOME`).

## Uninstall

`make uninstall` removes the symlink. It does not delete `~/.symphony` or any worktrees; remove tasks first with `symphony clean <task>`.

## If you moved or renamed this folder

Run `make install` again from the new location; the symlink points at the old path.
