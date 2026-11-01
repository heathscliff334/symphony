---
name: symphony
description: Fan tasks out to other agent CLIs (claude, codex, agy, mcode, opencode) in parallel, each in its own git worktree, then wait and collect each task's outcome. Use when the user asks to run work on several agents or models at once, get second opinions from other agents, compare models, or coordinate workers, without the Orca app. Not for single hand-offs to one agent.
---

# symphony

symphony is a CLI on PATH (`~/.local/bin/symphony`). Before running anything, load the full guide:

```bash
symphony guide
```

Follow it. If `symphony` is not found, install it: run `make install` in `/Users/kevin/Developments/projects/skills/symphony` (see `AGENTS.md` there).

Do not start real agents unless the user asked for that.
