#!/usr/bin/env python3
"""symphony: harness-agnostic task fan-out. One file, stdlib only. See `symphony guide`."""
import argparse, json, os, re, shutil, signal, subprocess, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path

from adapters import build_argv, HARNESSES

PREAMBLE = (
    'You are an symphony worker. Task: {task_id}. Work only in {cwd}.\n'
    'Do only the task below. Do not ask questions; make a reasonable choice and note it.\n'
    'Your final message MUST end with exactly one line:\n'
    'SYMPHONY_RESULT {{"outcome":"succeeded"|"failed","summary":"<3 sentences>"}}\n'
    '--- TASK ---\n{spec}')
RESULT_RE = re.compile(r'^SYMPHONY_RESULT (\{.*\})$')
START_GRACE_S = 15  # a supervisor with no pid yet is presumed starting for this long


class Die(Exception):
    pass


# ---------- store ----------

def home():
    return Path(os.environ.get("SYMPHONY_HOME") or Path.home() / ".symphony")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def age_s(iso):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()


def write_json(path, obj):
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    os.replace(tmp, path)


def read_json(path):
    return json.loads(path.read_text())


def get_meta(tdir):
    return read_json(tdir / "meta.json")


def set_meta(tdir, **kv):
    # shortcut: read-modify-write without a lock, relies on one writer at a time per task; upgrade if two writers appear
    m = get_meta(tdir)
    m.update(kv)
    write_json(tdir / "meta.json", m)


def find_task(task):
    if not re.fullmatch(r"t-[0-9a-f]{8}", task):
        raise Die(f"bad task id: {task}")
    hits = list(home().glob(f"runs/*/tasks/{task}"))
    if not hits:
        raise Die(f"no such task: {task}")
    return hits[0]


def pick_run(run):
    if not run:
        f = home() / "latest"
        if not f.exists():
            raise Die("no run yet; create one with: symphony run new \"<objective>\"")
        run = f.read_text().strip()
    if not re.fullmatch(r"r-[0-9a-f]{8}", run) or not (home() / "runs" / run).is_dir():
        raise Die(f"no such run: {run}")
    return run


def run_tasks(run):
    return sorted((home() / "runs" / run / "tasks").glob("t-*"), key=lambda p: p.stat().st_mtime)


def settle(tdir, outcome, summary, reason=None):
    """Write result.json exactly once (link fails if it exists). True if we won."""
    res = {"task": tdir.name, "outcome": outcome, "summary": summary, "reason": reason, "settled_at": now()}
    tmp = tdir / f".result.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(res))
    try:
        os.link(tmp, tdir / "result.json")
    except FileExistsError:
        return False
    finally:
        tmp.unlink()
    set_meta(tdir, state=outcome)
    return True


def alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def kill_group(pid):
    # shortcut: trusts the stored pid, a reused pid could be hit; upgrade by also storing process start time
    if not alive(pid):
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        for _ in range(20):
            if not alive(pid):
                return
            time.sleep(0.1)


def reconcile(tdir):
    """Settle a task whose supervisor died without a result, so nothing stays 'running' forever."""
    if (tdir / "result.json").exists():
        return
    m = get_meta(tdir)
    sp = m.get("supervisor_pid")
    if sp is None and age_s(m["created"]) < START_GRACE_S:
        return
    if sp is not None and alive(sp):
        return
    kill_group(m.get("pid"))
    settle(tdir, "failed", "exited without report", "exited without report")


def view(tdir):
    """meta with state reflecting live truth."""
    reconcile(tdir)
    m = get_meta(tdir)
    rf = tdir / "result.json"
    if rf.exists():
        m["state"] = read_json(rf)["outcome"]
    return m


# ---------- commands ----------

def cmd_run_new(a):
    run = "r-" + uuid.uuid4().hex[:8]
    d = home() / "runs" / run
    (d / "tasks").mkdir(parents=True)
    write_json(d / "run.json", {"run": run, "objective": a.objective, "created": now()})
    (home() / "latest").write_text(run)
    print(run)


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def new_task(run, harness, spec, model, after, cwd, worktree, yolo, timeout, retry_of=None, allow_shell=False):
    if harness not in HARNESSES:
        raise Die(f"unknown harness {harness!r}; choose from: {', '.join(HARNESSES)}")
    cwd = Path(cwd).resolve()
    if not cwd.is_dir():
        raise Die(f"cwd is not a directory: {cwd}")
    if after:
        find_task(after)
    task = "t-" + uuid.uuid4().hex[:8]
    tdir = home() / "runs" / run / "tasks" / task
    tdir.mkdir(parents=True)
    repo, branch, work = str(cwd), None, cwd
    if worktree:
        if git(cwd, "rev-parse", "--git-dir").returncode != 0:
            shutil.rmtree(tdir)
            raise Die(f"{cwd} is not a git repo; pass --no-worktree to run in place")
        branch, work = f"symphony/{task}", tdir / "wt"
        r = git(cwd, "worktree", "add", "-b", branch, str(work))
        if r.returncode != 0:
            shutil.rmtree(tdir)
            raise Die(f"git worktree add failed: {r.stderr.strip()}")
    (tdir / "spec.md").write_text(spec)
    write_json(tdir / "meta.json", {
        "task": task, "run": run, "harness": harness, "model": model,
        "state": "blocked" if after else "running", "pid": None, "supervisor_pid": None,
        "cwd": str(work), "branch": branch, "after": after, "timeout_s": timeout, "yolo": yolo,
        "retry_of": retry_of, "created": now(), "repo": repo, "allow_shell": allow_shell})
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "_supervise", task],
                     start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     env={**os.environ, "SYMPHONY_HOME": str(home())})
    return task


def cmd_start(a):
    run = pick_run(a.run)
    spec = a.spec
    try:
        if os.path.isfile(spec):
            spec = Path(spec).read_text()
    except OSError:
        pass  # too long to be a path: treat as literal text
    print(new_task(run, a.harness, spec, a.model, a.after, a.cwd or os.getcwd(),
                   not a.no_worktree, a.yolo, a.timeout, allow_shell=a.allow_shell))


def cmd_wait(a):
    run = pick_run(a.run)
    deadline = time.time() + a.timeout
    while True:
        pending, fresh = False, []
        for t in run_tasks(run):
            reconcile(t)
            if not (t / "result.json").exists():
                pending = True
            elif not (t / "reported").exists():
                fresh.append(t)
        if fresh:
            for t in fresh:
                r = read_json(t / "result.json")
                print(f"{t.name} {r['outcome']} {' '.join(r['summary'].split())}")
                (t / "reported").touch()
            return
        if not pending:
            return
        if time.time() >= deadline:
            sys.exit(3)
        time.sleep(1)


def fmt_age(s):
    s = int(s)
    return f"{s}s" if s < 60 else f"{s // 60}m" if s < 3600 else f"{s // 3600}h"


def cmd_status(a):
    ms = [view(t) for t in run_tasks(pick_run(a.run))]
    if a.json:
        print(json.dumps(ms, indent=1))
        return
    print(f"{'TASK':<11} {'HARNESS':<9} {'STATE':<10} {'ALIVE':<5} AGE")
    for m in ms:
        up = "yes" if alive(m["pid"]) and m["state"] == "running" else "-"
        print(f"{m['task']:<11} {m['harness']:<9} {m['state']:<10} {up:<5} {fmt_age(age_s(m['created']))}")


def cmd_result(a):
    t = find_task(a.task)
    m = view(t)
    rf = t / "result.json"
    if not rf.exists():
        print(f"task: {a.task}\nstate: {m['state']} (not settled)\nlog: {t / 'log.txt'}")
        return
    r = read_json(rf)
    print(f"task: {a.task}\noutcome: {r['outcome']}\nsummary: {r['summary']}\nreason: {r['reason'] or '-'}")
    wt = t / "wt"
    if wt.is_dir():
        out = git(wt, "status", "--short").stdout.rstrip()
        print("files changed:\n" + (out or "  (none)"))
    else:
        print("files changed: (no worktree)")
    print(f"log: {t / 'log.txt'}")


def cmd_stop(a):
    t = find_task(a.task)
    if (t / "result.json").exists():
        raise Die(f"{a.task} already settled")
    m = get_meta(t)
    kill_group(m.get("supervisor_pid"))  # supervisor first, so it cannot settle the task itself
    kill_group(m.get("pid"))
    settle(t, "failed", "stopped", "stopped")
    print(f"{a.task} stopped")


def cmd_retry(a):
    t = find_task(a.task)
    m = get_meta(t)
    wt = m["branch"] is not None
    print(new_task(m["run"], m["harness"], (t / "spec.md").read_text(), m["model"], m["after"],
                   m["repo"] if wt else m["cwd"], wt, m["yolo"], m["timeout_s"], retry_of=a.task, allow_shell=m.get("allow_shell", False)))


def cmd_merge(a):
    t = find_task(a.task)
    m = view(t)
    if not m["branch"]:
        raise Die("task ran without a worktree; nothing to merge")
    rf = t / "result.json"
    if not rf.exists():
        raise Die("task has not settled yet")
    if read_json(rf)["outcome"] != "succeeded" and not a.force:
        raise Die("task did not succeed; read `symphony result`, then use --force to merge anyway")
    wt, repo, branch = t / "wt", m["repo"], m["branch"]
    if not wt.is_dir():
        raise Die("worktree is gone (cleaned?)")
    ident = ["-c", "user.name=symphony", "-c", "user.email=symphony@localhost"]
    git(wt, "add", "-A")
    if git(wt, "status", "--porcelain").stdout.strip():
        r = git(wt, *ident, "commit", "-m", f"symphony {a.task}: {' '.join(read_json(rf)['summary'].split())[:72]}")
        if r.returncode != 0:
            raise Die(f"commit in worktree failed: {r.stderr.strip()}")
    if git(repo, "rev-list", "--count", branch, "^HEAD").stdout.strip() == "0":
        print(f"{a.task}: nothing to merge")
        return
    r = git(repo, *ident, "merge", "--no-ff", "-m", f"symphony: merge {a.task}", branch)
    if r.returncode != 0:
        files = git(repo, "diff", "--name-only", "--diff-filter=U").stdout.split()
        git(repo, "merge", "--abort")  # leave the repo clean; a half-done merge is worse than none
        if files:
            raise Die(f"merge conflict in: {', '.join(files)}. Repo left unchanged. Resolve by hand: git -C {repo} merge {branch}")
        raise Die(f"merge failed: {(r.stderr or r.stdout).strip()}")
    print(f"merged {branch} into {git(repo, 'rev-parse', '--abbrev-ref', 'HEAD').stdout.strip()}")


def cmd_clean(a):
    t = find_task(a.task)
    wt = t / "wt"
    if not wt.is_dir():
        print("nothing to clean")
        return
    if not a.force:
        if not (t / "result.json").exists():
            raise Die("task still running; use --force")
        if git(wt, "status", "--porcelain").stdout.strip():
            raise Die("worktree has uncommitted changes; use --force")
    r = git(get_meta(t)["repo"], "worktree", "remove", "--force", str(wt))
    if r.returncode != 0:
        raise Die(f"git worktree remove failed: {r.stderr.strip()}")
    print(f"removed {wt}")


def cmd_guide(a):
    g = Path(__file__).resolve().parent / "GUIDE.md"
    if not g.exists():
        raise Die(f"GUIDE.md not found next to symphony.py ({g})")
    sys.stdout.write(g.read_text())


# shortcut: only two agents have a known skills folder; any other agent uses --dir, add a name here once its folder is confirmed
SKILL_DIRS = {"claude": Path.home() / ".claude" / "skills", "agents": Path.home() / ".agents" / "skills",
              "antigravity": Path.home() / ".gemini" / "config" / "skills"}


def skill_targets(a):
    names = a.agent or ([] if a.dir else list(SKILL_DIRS))
    return [SKILL_DIRS[n] for n in names] + [Path(d).expanduser() for d in a.dir]


def skill_src():
    s = Path(__file__).resolve().parent / "skill"
    if not (s / "SKILL.md").exists():
        raise Die(f"skill/SKILL.md not found next to symphony.py ({s})")
    return s


def cmd_install(a):
    src = skill_src()
    for base in skill_targets(a):
        link = base / "symphony"
        if link.is_symlink() and link.resolve() == src:
            print(f"ok      {link} (already linked)")
            continue
        if link.exists() or link.is_symlink():
            if not a.force:
                raise Die(f"{link} already exists and is not this skill; use --force to replace it")
            link.unlink() if link.is_symlink() else shutil.rmtree(link)
        base.mkdir(parents=True, exist_ok=True)
        link.symlink_to(src)
        print(f"linked  {link} -> {src}")


def cmd_uninstall(a):
    src = skill_src()
    for base in skill_targets(a):
        link = base / "symphony"
        if not link.is_symlink():
            print(f"skip    {link} (not installed)" if not link.exists() else f"skip    {link} (not a link; left alone)")
        elif link.resolve() != src:
            print(f"skip    {link} (points elsewhere; left alone)")
        else:
            link.unlink()
            print(f"removed {link}")


# ---------- supervisor ----------

def last_result(log):
    for line in reversed(log.read_text(errors="replace").splitlines()):
        mt = RESULT_RE.match(line.rstrip())
        if not mt:
            continue
        try:
            r = json.loads(mt.group(1))
        except ValueError:
            continue
        if r.get("outcome") in ("succeeded", "failed") and isinstance(r.get("summary"), str):
            return r
    return None


def cmd_supervise(a):
    t = find_task(a.task)
    done = t / "result.json"
    m = get_meta(t)
    set_meta(t, supervisor_pid=os.getpid())
    if m["after"]:
        pdir = find_task(m["after"])
        while not (pdir / "result.json").exists():
            if done.exists():
                return
            reconcile(pdir)
            time.sleep(1)
        if read_json(pdir / "result.json")["outcome"] != "succeeded":
            settle(t, "failed", "parent failed", "parent failed")
            return
    if done.exists():  # stopped while blocked
        return
    prompt = PREAMBLE.format(task_id=t.name, cwd=m["cwd"], spec=(t / "spec.md").read_text())
    argv = build_argv(m["harness"], prompt, m["cwd"], m["model"], m["yolo"], m.get("allow_shell", False))
    try:
        with open(t / "log.txt", "ab") as log:
            p = subprocess.Popen(argv, cwd=m["cwd"], stdin=subprocess.DEVNULL, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
    except OSError as e:
        settle(t, "failed", f"spawn failed: {e}", "spawn failed")
        return
    # shortcut: tiny window before pid is stored in which `stop` cannot find the worker; the done-file poll below still reaps it
    set_meta(t, state="running", pid=p.pid)
    deadline = time.time() + m["timeout_s"]
    while True:
        try:
            p.wait(timeout=1)
            break
        except subprocess.TimeoutExpired:
            pass
        if done.exists():  # settled externally (stop / reconcile)
            kill_group(p.pid)
            p.wait()
            return
        if time.time() >= deadline:
            kill_group(p.pid)
            p.wait()
            settle(t, "failed", "timeout", "timeout")
            return
    r = last_result(t / "log.txt")
    if r:
        settle(t, r["outcome"], r["summary"])
    else:
        settle(t, "failed", "exited without report", "exited without report")


# ---------- cli ----------

def main():
    ap = argparse.ArgumentParser(prog="symphony", description="Fan tasks out to AI agent CLIs.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        p = sub.add_parser(name, **kw)
        p.set_defaults(fn=fn)
        return p

    run = add("run", None, help="run management").add_subparsers(dest="sub", required=True)
    p = run.add_parser("new", help="create a run, print its id")
    p.add_argument("objective")
    p.set_defaults(fn=cmd_run_new)

    p = add("start", cmd_start, help="start a task, print its id")
    p.add_argument("--harness", required=True)
    p.add_argument("--spec", required=True, help="file path, or literal text")
    p.add_argument("--model")
    p.add_argument("--after", metavar="TASK")
    p.add_argument("--cwd")
    p.add_argument("--no-worktree", action="store_true")
    p.add_argument("--yolo", action="store_true")
    p.add_argument("--allow-shell", action="store_true", help="let the worker run any shell command (claude, agy); file edits stay governed by the default mode")
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--run")

    p = add("wait", cmd_wait, help="block until a task settles")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--run")

    p = add("status", cmd_status, help="list tasks")
    p.add_argument("--json", action="store_true")
    p.add_argument("--run")

    for name, fn, h in (("result", cmd_result, "show a task's outcome"), ("stop", cmd_stop, "stop a task"),
                        ("retry", cmd_retry, "start a fresh attempt"), ("merge", cmd_merge, "commit the worktree and merge its branch into the repo"),
                        ("clean", cmd_clean, "remove the worktree")):
        p = add(name, fn, help=h)
        p.add_argument("task")
        if name in ("clean", "merge"):
            p.add_argument("--force", action="store_true")
    add("guide", cmd_guide, help="print the usage guide")
    for name, fn, h in (("install", cmd_install, "link the symphony skill into agents' skills folders"),
                        ("uninstall", cmd_uninstall, "remove those links")):
        p = add(name, fn, help=h)
        p.add_argument("--agent", action="append", choices=sorted(SKILL_DIRS), help="default: all known agents (no --dir given)")
        p.add_argument("--dir", action="append", default=[], metavar="SKILLS_DIR", help="any other agent's skills folder (repeatable)")
        if name == "install":
            p.add_argument("--force", action="store_true", help="replace an existing 'symphony' entry")
    add("_supervise", cmd_supervise, help=argparse.SUPPRESS).add_argument("task")

    a = ap.parse_args()
    try:
        a.fn(a)
    except Die as e:
        print(f"symphony: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
