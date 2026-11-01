"""Run sequential, isolated smoke tests of installed harnesses."""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
from adapters import HARNESSES, build_argv

SPEC = 'Create hello.txt containing the text hi, then end your final reply with the single line: SYMPHONY_RESULT {"outcome":"succeeded","summary":"created hello.txt"}'
REPORT = Path(__file__).with_name('PHASE0_RESULTS.md')


def safe_lines(output):
    # Do not persist authentication diagnostics or arbitrary model output.
    lines = output.splitlines()[-5:]
    return '<br>'.join('`' + (line.replace('`', "'").replace('|', '&#124;')[:200] if re.fullmatch(r'SYMPHONY_RESULT \{"outcome":\s*"succeeded",\s*"summary":\s*"created hello.txt"\}', line.strip()) else '[output redacted]') + '`' for line in lines) or '—'


def attempt(name, yolo=False):
    repo = Path(tempfile.mkdtemp(prefix='symphony-phase0-'))
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    try:
        p = subprocess.run(build_argv(name, SPEC, str(repo), yolo=yolo), cwd=repo,
                           capture_output=True, text=True, errors='replace', timeout=300)
        stdout, stderr, code = p.stdout, p.stderr, str(p.returncode)
    except subprocess.TimeoutExpired as exc:
        def decode(s):
            return s.decode(errors='replace') if isinstance(s, bytes) else (s or '')
        stdout, stderr, code = decode(exc.stdout), decode(exc.stderr), 'timeout'
    except OSError as exc:
        stdout, stderr, code = '', type(exc).__name__, 'launch error'
    created = (repo / 'hello.txt').is_file()
    found = bool(re.search(r'^SYMPHONY_RESULT \{.*\}$', stdout, re.M))
    output = stdout + ('\n' + stderr if stderr else '')
    # Only retry when the output explicitly identifies permission denial and no
    # other identified failure; a generic timeout is not evidence of approval.
    approval = bool(re.search(r'(permission denied|approval (?:required|denied)|requires? (?:user )?approval)', output, re.I))
    return (name, 'yolo' if yolo else 'default', 'pass' if created and found and code == '0' else 'fail', 'yes' if created else 'no', 'yes' if found else 'no', code, safe_lines(output)), approval and not created and not found


def write(rows):
    text = '# Phase 0 results\n\nSequential tests in fresh temporary git repositories; output is redacted except the exact expected result line to avoid storing secrets. A pass requires a file, a result line, and exit code 0.\n\n'
    text += '| Harness | Mode | Result | hello.txt | Result line | Exit | Last 5 output lines (sanitized) |\n|---|---|---|---|---|---|---|\n'
    text += ''.join('| ' + ' | '.join(row) + ' |\n' for row in rows)
    text += '\n## Matrix corrections\n\n- OpenCode supports `--auto` for auto-approving permissions not explicitly denied; default permissions remain governed by its configuration.\n'
    REPORT.write_text(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', help='comma-separated harnesses')
    args = parser.parse_args()
    names = args.only.split(',') if args.only else [h for h in HARNESSES if h != 'fake']
    if any(h not in HARNESSES or h == 'fake' for h in names):
        parser.error('unknown or fake harness')
    rows = []
    for name in names:
        print('Testing', name, flush=True)
        row, retry = attempt(name)
        rows.append(row)
        write(rows)
        if retry:
            row, _ = attempt(name, True)
            rows.append(row)
            write(rows)
    write(rows)


if __name__ == '__main__':
    main()
