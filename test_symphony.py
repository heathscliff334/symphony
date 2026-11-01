"""Black-box tests: parallelism, worktree isolation, merge. Uses a fake harness only (no real agents)."""
import os, subprocess, sys, tempfile, time, unittest
from pathlib import Path

SYM = str(Path(__file__).resolve().parent / "symphony.py")

# Fake worker. Directives, one per line in the spec: "FAKE: sleep N", "FAKE: line N TEXT" (rewrite line N of shared.txt).
FAKE = '''#!/usr/bin/env python3
import re, sys, time
from pathlib import Path
prompt, cwd = sys.argv[1], sys.argv[2]
for n in re.findall(r"^FAKE: sleep (\\d+)$", prompt, re.M):
    time.sleep(int(n))
for n, text in re.findall(r"^FAKE: line (\\d+) (.+)$", prompt, re.M):
    f = Path(cwd, "shared.txt"); lines = f.read_text().splitlines()
    lines[int(n) - 1] = text; f.write_text("\\n".join(lines) + "\\n")
print('SYMPHONY_RESULT {"outcome":"succeeded","summary":"ok"}')
'''


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        fake = self.tmp / "fake.py"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        self.env = {**os.environ, "SYMPHONY_HOME": str(self.tmp / "home"), "SYMPHONY_FAKE_BIN": str(fake)}
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        (self.repo / "shared.txt").write_text("a\nb\nc\n")
        self.git("add", ".")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        self.sym("run", "new", "test")

    def git(self, *a):
        return subprocess.run(["git", "-C", str(self.repo), *a], capture_output=True, text=True)

    def sym(self, *a):
        return subprocess.run([sys.executable, SYM, *a], capture_output=True, text=True, env=self.env)

    def start(self, spec, *extra):
        r = self.sym("start", "--harness", "fake", "--cwd", str(self.repo), "--spec", spec, *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def wait_all(self, limit=30):
        end = time.time() + limit
        while time.time() < end:
            r = self.sym("wait", "--timeout", "5")
            if r.returncode == 0 and not r.stdout:
                return
        self.fail("tasks did not settle")

    def shared(self):
        return (self.repo / "shared.txt").read_text().splitlines()

    def test_tasks_run_in_parallel(self):
        t0 = time.time()
        for _ in range(3):
            self.start("FAKE: sleep 3", "--no-worktree")
        self.wait_all()
        self.assertLess(time.time() - t0, 7, "3 x 3s tasks must overlap (serial would be 9s+)")

    def test_worktrees_isolate_and_merge_cleanly(self):
        a = self.start("FAKE: line 1 A-edit")
        b = self.start("FAKE: line 3 C-edit")
        self.wait_all()
        self.assertEqual(self.shared(), ["a", "b", "c"], "main folder untouched while workers edit")
        self.assertEqual(self.sym("merge", a).returncode, 0)
        r = self.sym("merge", b)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.shared(), ["A-edit", "b", "C-edit"])

    def test_same_line_conflict_is_reported_and_repo_left_clean(self):
        a = self.start("FAKE: line 2 from-A")
        b = self.start("FAKE: line 2 from-B")
        self.wait_all()
        self.assertEqual(self.sym("merge", a).returncode, 0)
        r = self.sym("merge", b)
        self.assertEqual(r.returncode, 1)
        self.assertIn("conflict", r.stderr)
        self.assertIn("shared.txt", r.stderr)
        self.assertEqual(self.git("status", "--porcelain").stdout.strip(), "", "no half-done merge left behind")
        self.assertEqual(self.shared(), ["a", "from-A", "c"])

    def test_merge_refuses_unsettled_and_no_worktree_tasks(self):
        t = self.start("FAKE: sleep 4")
        self.assertEqual(self.sym("merge", t).returncode, 1)  # still running
        self.wait_all()
        n = self.start("FAKE: sleep 0", "--no-worktree")
        self.wait_all()
        r = self.sym("merge", n)
        self.assertEqual(r.returncode, 1)
        self.assertIn("without a worktree", r.stderr)


if __name__ == "__main__":
    unittest.main()
