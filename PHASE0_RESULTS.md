# Phase 0 results

Sequential tests in fresh temporary git repositories; output is redacted except the exact expected result line to avoid storing secrets. A pass requires a file, a result line, and exit code 0.

| Harness | Mode | Result | hello.txt | Result line | Exit | Last 5 output lines (sanitized) |
|---|---|---|---|---|---|---|
| claude | default | pass | yes | yes | 0 | `[output redacted]`<br>`[output redacted]`<br>`SYMPHONY_RESULT {"outcome":"succeeded","summary":"created hello.txt"}` |
| codex | default | pass | yes | yes | 0 | `SYMPHONY_RESULT {"outcome":"succeeded","summary":"created hello.txt"}`<br>`[output redacted]`<br>`[output redacted]`<br>`[output redacted]`<br>`[output redacted]` |
| agy | default | pass | yes | yes | 0 | `[output redacted]`<br>`[output redacted]`<br>`SYMPHONY_RESULT {"outcome":"succeeded","summary":"created hello.txt"}` |
| mcode | default | pass | yes | yes | 0 | `[output redacted]`<br>`[output redacted]`<br>`[output redacted]`<br>`[output redacted]`<br>`SYMPHONY_RESULT {"outcome":"succeeded","summary":"created hello.txt"}` |
| cmd | default | fail | no | yes | 0 | `[output redacted]`<br>`[output redacted]`<br>`[output redacted]` |
| opencode | default | pass | yes | yes | 0 | `[output redacted]`<br>`[output redacted]`<br>`[output redacted]`<br>`[output redacted]`<br>`[output redacted]` |

## Matrix corrections

- OpenCode supports `--auto` for auto-approving permissions not explicitly denied; default permissions remain governed by its configuration.
