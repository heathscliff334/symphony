# symphony guide (for the coordinating agent)

symphony fans tasks out to other agent CLIs, one git worktree per task, and reports each task's outcome. You are the coordinator: you write the task specs, start the workers, wait, read results, and merge. Workers never talk to you mid-task; they run once and report once.

Harnesses: `claude`, `codex`, `agy`, `mcode`, `cmd`, `opencode`. Known status: the first five (minus `cmd`) passed the headless test; `cmd` reported success without making the file, so avoid it for editing work.

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

Start every independent task before the first `wait`. `start` returns at once and each worker runs in its own detached process, so all started tasks run in parallel; you manage them all with `wait`, `status`, `result`, `stop`.

Useful options on `start`: `--model <id>`, `--after <task>` (run only after that task succeeds; if it fails, this one fails with "parent failed"), `--cwd <dir>`, `--no-worktree` (run in place; needed outside a git repo), `--timeout <seconds>` (default 1800), `--allow-shell`, `--yolo`.

`--allow-shell` lets a claude or agy worker run any shell command (e.g. `git log | head`); without it headless agy auto-denies commands and the task fails with "exited without report". File edits stay under the default mode. Use it only when the task needs shell and the user is fine with that; it is narrower than `--yolo`.

Other commands: `symphony stop <task>`, `symphony retry <task>` (new attempt, same spec and options).

## Writing a spec

Each spec must stand alone, because the worker sees nothing else. Name:

- **Target:** files or component in scope.
- **Change:** the concrete result to produce.
- **Constraints:** what must not change.
- **Ownership:** which files this worker may edit. Give parallel workers disjoint files.
- **Acceptance:** the test or output that proves it is done.

symphony adds the result-line instruction itself; do not repeat it.

## Rules

- A task succeeds only if the worker's final message ends with a `SYMPHONY_RESULT {...}` line. No line means `failed: exited without report`, even if the work is fine. Run `symphony result <task>` and look at the diff before you retry.
- `wait` exits 3 on timeout with nothing settled. That is a checkpoint, not a failure. Check `symphony status`, then wait again.
- A timeout or silence is not proof the worker died. Use `status` to see if its process is alive before you `stop` or `retry`.
- Never put two editing workers in one folder without worktrees. Worktrees are the default inside a git repo: each worker edits its own copy on branch `symphony/<task>`, so parallel workers cannot overwrite each other's files, even the same file.
- A worktree starts from the last commit, not from uncommitted changes in the user's folder. Tell the user to commit or stash first if the workers need their latest edits.
- Same-file edits collide only at merge time. Give workers disjoint parts of a file where you can; edits to different lines merge cleanly.
- Use `--yolo` only if the user asked. It lets a worker run any command in its worktree.
- Read each result and diff, then `symphony merge <task>`, one task at a time. It commits the worker's changes and merges the branch into the repo's current branch. On a conflict it aborts, leaves the repo unchanged, and names the conflicting files: resolve by hand (`git merge symphony/<task>`) or retry that task after the others are merged. It refuses a failed task unless `--force`.
- Do not run real agents just to test symphony unless the user asks; every run uses their accounts.

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
