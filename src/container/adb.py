"""adb device orchestration with the OPPO/Realme-specific gotchas baked in.

Known quirks (discovered empirically, all still true on this device):
  * adb backup returns an EMPTY archive if the app is force-stopped -> the
    app must be RUNNING when we fetch.
  * adb restore silently writes nothing if the restore parser hits an
    illegal path (see ab.py). "Full restore pass complete" in logcat is
    necessary but NOT sufficient -- always verify by re-fetching.
  * adb restore needs the app FORCE-STOPPED and the screen awake. The user
    must press "Restore my data" in the confirmation dialog.
  * NEVER force-stop com.android.backupconfirm before restoring; doing so
    destroys the confirm activity and aborts the restore.
  * pm clear is blocked on this ROM (no CLEAR_APP_USER_DATA permission).
    A full data wipe can only be done manually: Settings -> Apps ->
    Treasure of Nadia -> Storage -> Clear data.
"""

import re
import subprocess
import time


class AdbError(Exception):
    pass


def run(args: list[str], timeout: int = 60) -> str:
    proc = subprocess.run(["adb", *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise AdbError(f"adb {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def pidof(package: str) -> str:
    try:
        return run(["shell", "pidof", package]).strip()
    except AdbError:
        return ""


def is_running(package: str) -> bool:
    return bool(pidof(package))


def force_stop(package: str) -> None:
    run(["shell", "am", "force-stop", package])
    # give the process a moment to actually die
    for _ in range(10):
        if not is_running(package):
            return
        time.sleep(0.3)
    raise AdbError(f"app {package} still running after force-stop")


def wake_screen() -> None:
    run(["shell", "input", "keyevent", "KEYCODE_WAKEUP"])
    time.sleep(1)
    run(["shell", "input", "keyevent", "KEYCODE_WAKEUP"])


def backup(package: str, out_path: str, noapk: bool = True, noshared: bool = True) -> int:
    """adb backup. The app MUST be running or the archive is empty."""
    if not is_running(package):
        raise AdbError(f"app {package} is not running; start it first (backup of a stopped app is empty)")
    args = ["backup", "-f", out_path]
    if noapk:
        args.append("-noapk")
    if noshared:
        args.append("-noshared")
    args.append(package)
    # Backup waits on the device confirmation dialog; it can take a while.
    run(args, timeout=120)
    return 0


def restore(ab_path: str, package: str, timeout: int = 120) -> None:
    """adb restore. The app MUST be force-stopped; user presses "Restore my data".

    Does NOT touch com.android.backupconfirm (killing it aborts the restore).
    """
    if is_running(package):
        raise AdbError(f"app {package} is running; force-stop it before restore")
    wake_screen()
    run(["restore", ab_path], timeout=timeout)


def last_restore_log(limit: int = 20000) -> str:
    """Tail of logcat filtered to restore-relevant lines."""
    out = run(["logcat", "-d"], timeout=60)
    lines = []
    for line in out.splitlines():
        if re.search(r"BackupManagerService|Full restore|restore processing|Parse error|Illegal semantic", line):
            lines.append(line)
    return "\n".join(lines[-limit:])


def restore_ok(log: str) -> bool:
    return "Full restore pass complete." in log and "Parse error" not in log
