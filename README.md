# symphony

Fan tasks out to other agent CLIs (claude, codex, agy, mcode, opencode, cmd) in parallel, each in its own git worktree, then wait and collect each task's outcome.

symphony is a single-file, stdlib-only Python CLI. It is the coordinator: you write task specs, start the workers, wait, read results, and merge. Workers never talk to you mid-task — they run once and report once.

## Requirements

- macOS or Linux
- `python3` 3.9+
- `git`
- `make`

No packages to install.

## Install

```bash
git clone https://github.com/heathscliff334/symphony.git
cd symphony
make install
```

This symlinks `~/.local/bin/symphony` to `symphony.py`. It needs no sudo.

Make sure `~/.local/bin` is on your `PATH`:

```bash
echo "$PATH" | tr ':' '\n' | grep -x "$HOME/.local/bin"
```

If it prints nothing, add this to your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Quick check

No real agent needed — this uses a fake harness:

```bash
cd /tmp && T=$(mktemp -d) && mkdir $T/w
printf '#!/bin/sh\necho '"'"'SYMPHONY_RESULT {"outcome":"succeeded","summary":"ok"}'"'"'\n' > $T/fake.sh && chmod +x $T/fake.sh
SYMPHONY_HOME=$T/home SYMPHONY_FAKE_BIN=$T/fake.sh sh -c '
  symphony run new check >/dev/null &&
  symphony start --harness fake --no-worktree --cwd '"$T"'/w --spec x >/dev/null &&
  symphony wait --timeout 20'
```

Success is one line ending in `succeeded ok`, exit code 0.

## Install the skill for agents

`symphony install` links the bundled skill into Claude Code (`~/.claude/skills`), the shared agents folder (`~/.agents/skills`, used by Codex) and Antigravity (`~/.gemini/config/skills`). It is safe to repeat and refuses to overwrite anything that is not this skill.

```bash
symphony install                 # all three
symphony install --agent claude  # one agent only
symphony install --dir <skills-folder>  # any other agent
symphony uninstall               # remove the links
```

Restart the agent's session afterwards; skill lists load at session start.

## The loop

```bash
symphony run new "<objective>"                      # once per job; later commands use the latest run

a=$(symphony start --harness claude --spec "<spec>")   # prints a task id, returns at once
b=$(symphony start --harness codex  --spec "<spec>" --model gpt-6.1-terra)
symphony wait                                       # blocks; prints "<task> <outcome> <summary>" per newly settled task
symphony wait                                       # repeat until it prints nothing (all settled)

symphony status [--json]                            # all tasks: state, pid, harness
symphony result <task>                              # outcome, summary, reason, files changed, log path
symphony merge <task>                               # commit the worker's changes, merge its branch into the repo
symphony clean <task>                               # remove the worktree (refuses if dirty; --force to override)
```

Start every independent task before the first `wait`. `start` returns at once and each worker runs in its own detached process, so all started tasks run in parallel.

Useful options on `start`: `--model <id>`, `--after <task>` (run only after that task succeeds), `--cwd <dir>`, `--no-worktree` (run in place; needed outside a git repo), `--timeout <seconds>` (default 1800), `--allow-shell`, `--yolo`.

Other commands: `symphony stop <task>`, `symphony retry <task>`, `symphony guide` (prints the full coordinator guide).

## Writing a spec

Each spec must stand alone, because the worker sees nothing else. Name:

- **Target:** files or component in scope.
- **Change:** the concrete result to produce.
- **Constraints:** what must not change.
- **Ownership:** which files this worker may edit. Give parallel workers disjoint files.
- **Acceptance:** the test or output that proves it is done.

symphony adds the result-line instruction itself; do not repeat it.

## Example: three workers

```bash
symphony run new "add rate limiting"
a=$(symphony start --harness claude --spec "Target: src/limiter.py. Change: add a token-bucket limiter class RateLimiter(rate, burst). Constraints: stdlib only. Ownership: src/limiter.py only. Acceptance: python -c 'from src.limiter import RateLimiter' works.")
b=$(symphony start --harness codex --after $a --spec "Target: tests/test_limiter.py. Change: tests for RateLimiter. Ownership: that file only. Acceptance: pytest tests/test_limiter.py passes.")
c=$(symphony start --harness agy --spec "Review src/ for places that should be rate limited. Write findings to REVIEW.md. Edit nothing else.")
symphony wait; symphony wait; symphony wait
symphony result $a; symphony result $b; symphony result $c
```

Then read each diff, merge the good branches, and run `symphony clean <task>` on each.

## Rules

- A task succeeds only if the worker's final message ends with a `SYMPHONY_RESULT {...}` line. No line means `failed: exited without report`, even if the work is fine. Run `symphony result <task>` and look at the diff before you retry.
- `wait` exits 3 on timeout with nothing settled. That is a checkpoint, not a failure. Check `symphony status`, then wait again.
- Never put two editing workers in one folder without worktrees. Worktrees are the default inside a git repo: each worker edits its own copy on branch `symphony/<task>`, so parallel workers cannot overwrite each other's files.
- A worktree starts from the last commit, not from uncommitted changes in your folder. Commit or stash first if the workers need your latest edits.
- Same-file edits collide only at merge time. Give workers disjoint parts of a file where you can; edits to different lines merge cleanly.
- Use `--yolo` only if the user asked. It lets a worker run any command in its worktree.
- Read each result and diff, then `symphony merge <task>`, one task at a time. It commits the worker's changes and merges the branch into the repo's current branch. On a conflict it aborts, leaves the repo unchanged, and names the conflicting files. It refuses a failed task unless `--force`.
- Do not run real agents just to test symphony; every run uses their accounts and quota.

## Harness status

From `PHASE0_RESULTS.md`: `claude`, `codex`, `agy`, `mcode` and `opencode` passed the headless test. `cmd` reported success without creating the file, so avoid it for editing work.

## Development

```bash
make test            # python3 -m unittest discover -s .
make install-skill   # link the skill into agents (same as `symphony install`)
make uninstall       # remove the symlink
```

Data lives in `~/.symphony` (override with `SYMPHONY_HOME`).

## License

[MIT](LICENSE)
