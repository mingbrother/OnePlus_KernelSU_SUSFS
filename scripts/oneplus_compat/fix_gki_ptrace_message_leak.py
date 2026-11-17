#!/usr/bin/env python3
"""Relocate the ptrace_message clear emitted by WildKernels' gki_ptrace.patch.

Why this exists
---------------
`common/gki_ptrace.patch` (kernel_patches, dated 2025-05-28) is an anti-leak
hardening: it threads `message` through ptrace_notify()/ptrace_stop() and clears
`task->ptrace_message` at three places so a stale PID (e.g. a dead zygote
leader) cannot be read back through PTRACE_GETEVENTMSG.

One of those three places is the top of ptrace_check_attach():

	int ret = -ESRCH;
	child->ptrace_message = 0;      <-- inserted by the patch
	read_lock(&tasklist_lock);
	if (child->ptrace && child->parent == current) {
		if (ignore_state || ptrace_freeze_traced(child))
			ret = 0;

`ptrace_freeze_traced()` calls `looks_like_a_spurious_pid()`, and upstream 5.15
uses ptrace_message there to tell a real PTRACE_EVENT_EXEC stop from a stale
event belonging to a previous thread-group leader:

static bool looks_like_a_spurious_pid(struct task_struct *task)
{
	if (task->exit_code != ((PTRACE_EVENT_EXEC << 8) | SIGTRAP))
		return false;
	if (task_pid_vnr(task) == task->ptrace_message)
		return false;               /* message == self  -> real event */
	return true;                    /* otherwise        -> stale */
}

Because the patch clears ptrace_message *before* that check runs, every real
exec-stop now looks stale: ptrace_freeze_traced() returns false,
ptrace_check_attach() returns -ESRCH, so PTRACE_CONT / PTRACE_GETREGSET /
PTRACE_DETACH all fail and the tracee never leaves TASK_TRACED. The tracer that
attached it (crash_dump, a monitoring daemon, ...) cannot resume or detach it -
the process simply freezes with no tombstone and no FATAL log.

This script keeps the hardening and moves the clear to after the decision:

	if (!ret)
		child->ptrace_message = 0;

Idempotent, and a no-op when the patch is absent or already fixed.
"""

import sys
from pathlib import Path

EARLY = "\tint ret = -ESRCH;\n\tchild->ptrace_message = 0;\n"
ANCHOR = "\treturn ret;\n}\n\nstatic bool ptrace_has_cap("
FIXED = ("\t/*\n"
         "\t * Clearing ptrace_message before ptrace_freeze_traced() would make\n"
         "\t * looks_like_a_spurious_pid() treat every real PTRACE_EVENT_EXEC stop\n"
         "\t * as stale (-ESRCH) and leave the tracee in TASK_TRACED forever, so\n"
         "\t * only drop the message once the stop has been validated.\n"
         "\t */\n"
         "\tif (!ret)\n"
         "\t\tchild->ptrace_message = 0;\n\n"
         "\treturn ret;\n}\n\nstatic bool ptrace_has_cap(")


def log(msg):
    print(f"[ptrace-fix] {msg}", flush=True)


def main():
    if len(sys.argv) < 2:
        print("usage: fix_gki_ptrace_message_leak.py <kernel-root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    path = root / "kernel/ptrace.c"
    if not path.is_file():
        log("kernel/ptrace.c not found; skip")
        return 0

    text = path.read_text(encoding="utf-8", errors="surrogateescape")

    if "if (!ret)\n\t\tchild->ptrace_message = 0;" in text:
        log("already fixed; nothing to do")
        return 0
    if EARLY not in text:
        log("early ptrace_message clear not present (patch not applied?); skip")
        return 0
    if text.count(ANCHOR) != 1:
        log(f"expected 1 anchor, found {text.count(ANCHOR)}; refusing to edit")
        return 1

    text = text.replace(EARLY, "\tint ret = -ESRCH;\n", 1)
    text = text.replace(ANCHOR, FIXED, 1)
    path.write_text(text, encoding="utf-8", errors="surrogateescape")
    log("moved the ptrace_message clear after the spurious-pid check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
