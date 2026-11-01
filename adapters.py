"""Argument-vector adapters for supported one-shot agent CLIs."""
import os

# Each entry: executable/command, ordinary permission flags, yolo flags,
# model flag, and optional working-directory flag.
ADAPTERS = {
    'claude': (['claude', '-p'], ['--permission-mode', 'acceptEdits'], ['--dangerously-skip-permissions'], '--model', None),
    # --skip-git-repo-check: without it codex refuses to run in a non-git folder (--no-worktree use).
    'codex': (['codex', 'exec', '--skip-git-repo-check'],['-s', 'workspace-write'], ['--dangerously-bypass-approvals-and-sandbox'], '-m', '-C'),
    'agy': (['agy', '-p'], ['--mode', 'accept-edits'], ['--dangerously-skip-permissions'], '--model', None),
    'mcode': (['mcode', 'exec'], ['--permission', 'smart'], ['--permission', 'full'], '--model', '--cwd'),
    'cmd': (['cmd', '-p'], ['--accept-edits'], ['--yolo'], '-m', None),
    # opencode uses its existing configuration for default permissions.
    'opencode': (['opencode', 'run'], [], ['--auto'], '-m', '--dir'),
    'fake': None,
}
HARNESSES = list(ADAPTERS)


# shortcut: shell allow-rules known for claude and agy only; the other harnesses already run commands under their own sandbox or config, check each before adding
SHELL_ALLOW = {
    'claude': ['--allowedTools=Bash'],
    'agy': ['--settings', '{"permissions":{"allow":["command(*)"]}}'],
}


def build_argv(harness, prompt, cwd, model=None, yolo=False, allow_shell=False):
    entry = ADAPTERS[harness]
    if harness == 'fake':
        return [os.environ['SYMPHONY_FAKE_BIN'], prompt, cwd]
    base, normal, bypass, model_flag, cwd_flag = entry
    # -p consumes the following argument for claude, agy and cmd.
    argv = base + ([prompt] if harness in ('claude', 'agy', 'cmd') else [])
    if harness == 'cmd':
        argv += ['-t', '--tools-all']
    argv += bypass if yolo else normal
    if allow_shell and not yolo:
        argv += SHELL_ALLOW.get(harness, [])
    if cwd_flag:
        argv += [cwd_flag, cwd]
    if model:
        argv += [model_flag, model]
    if harness not in ('claude', 'agy', 'cmd'):
        argv.append(prompt)
    return argv


if __name__ == '__main__':
    os.environ.setdefault('SYMPHONY_FAKE_BIN', 'fake')
    for name in HARNESSES:
        for yolo in (False, True):
            argv = build_argv(name, 'unique prompt', '/tmp', 'model', yolo)
            assert isinstance(argv, list) and all(isinstance(x, str) for x in argv)
            assert argv.count('unique prompt') == 1
    print('adapter self-check passed')
