"""abctl — single entry point for the treasure-edit toolchain.

    python -m abctl fetch  [app]                     pull current save off the device
    python -m abctl edit   <patch.json> [app]        build an edited .ab from the last fetch
    python -m abctl push   [app]                     restore the edited .ab (user confirms on device)
    python -m abctl verify [app]                     fetch again + diff against the patch (manual launch first)
    python -m abctl diff   <a.ab> <b.ab> [app]        show leveldb/JSON differences between two backups

Runtime overrides (edit only):
    --set money=50000000 --add-item 19 --del-item 95
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(REPO_ROOT, "config")
PATCH_DIR = os.path.join(REPO_ROOT, "patches")
WORK_DIR = os.path.join(REPO_ROOT, "work")
NODE = shutil.which("node") or "node"
APPLY_PATCH_JS = os.path.join(REPO_ROOT, "src", "cli", "apply_patch.js")

from container import ab as abmod
from container import adb
from container.rebuild import rebuild_to_ab


def load_cfg(app: str) -> dict:
    p = os.path.join(CONFIG_DIR, f"{app}.json")
    if not os.path.isfile(p):
        sys.exit(f"no config for app {app!r} (expected {p})")
    return json.load(open(p, encoding="utf-8"))


def app_id(cfg: dict) -> str:
    return cfg["app"]["id"]


def workdir_for(app: str) -> str:
    d = os.path.join(WORK_DIR, app)
    os.makedirs(d, exist_ok=True)
    return d


def latest_fetch(app: str):
    d = workdir_for(app)
    stamps = sorted(x for x in os.listdir(d) if x.startswith("fetch_"))
    if not stamps:
        return None
    return os.path.join(d, stamps[-1])


def run_node(args, timeout=60):
    return subprocess.run([NODE, *args], capture_output=True, text=True, timeout=timeout)


def cmd_fetch(cfg):
    pid = app_id(cfg)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = os.path.join(workdir_for(cfg["app"]["id"]), f"fetch_{stamp}")
    abfile = os.path.join(outdir, "source.ab")
    os.makedirs(outdir, exist_ok=True)
    adb.backup(pid, abfile)
    abmod.write_payload(abmod.read_payload(abfile), abfile)  # normalize
    print(f"fetched {abfile}")
    print("TIP: user must now open the game and confirm the backup dialog.")
    return abfile


def cmd_edit(cfg, patch_path, overrides):
    latest = latest_fetch(cfg["app"]["id"])
    if not latest:
        sys.exit("no fetch yet; run 'fetch' first")
    src_ab = os.path.join(latest, "source.ab")
    src_ldb = os.path.join(latest, "ldb_orig")
    mod_ldb = os.path.join(latest, "ldb_mod")

    # extract leveldb from source
    import io
    import tarfile
    import zlib
    tar_bytes = abmod.read_payload(src_ab)
    tf = tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:")
    ldb_rel = cfg["leveldb"]["rel_path"]
    ldb_prefix = ldb_rel + "/"
    os.makedirs(src_ldb, exist_ok=True)
    for m in tf.getmembers():
        if m.name == ldb_rel or m.name.startswith(ldb_prefix):
            name = m.name[len(ldb_rel) + 1:] if m.name.startswith(ldb_prefix) else ""
            if not name:
                continue
            target = os.path.join(src_ldb, name)
            if m.isreg():
                fh = tf.extractfile(m)
                with open(target, "wb") as out:
                    out.write(fh.read())
                fh.close()
            else:
                os.makedirs(target, exist_ok=True)
    tf.close()

    # apply overrides to patch
    patch = json.load(open(patch_path, encoding="utf-8"))
    for kv in overrides.set:
        k, _, v = kv.partition("=")
        if k == "money":
            patch["money"] = int(v)
        elif k == "moan":
            patch["moan"] = int(v)
        elif k == "kamasutra":
            patch["kamasutra"] = v
        else:
            sys.exit(f"unknown --set key {k!r} (supported: money, moan, kamasutra)")
    if overrides.add_item:
        patch["items"] = list(dict.fromkeys(patch.get("items", []) + overrides.add_item))
    if overrides.del_item:
        patch["items"] = [i for i in patch.get("items", []) if i not in overrides.del_item]

    patch_file = os.path.join(latest, "patch.json")
    json.dump(patch, open(patch_file, "w"), indent=2)

    cfg_file = os.path.join(CONFIG_DIR, f"{cfg['app']['name']}.json")
    r = run_node([APPLY_PATCH_JS, src_ldb, mod_ldb, patch_file, cfg_file])
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        sys.exit("apply_patch failed")

    out_ab = os.path.join(latest, "edited.ab")
    rebuild_to_ab(src_ab, mod_ldb, ldb_rel, out_ab)
    print(f"built {out_ab}")


def cmd_push(cfg):
    latest = latest_fetch(cfg["app"]["id"])
    if not latest:
        sys.exit("no fetch yet")
    edited = os.path.join(latest, "edited.ab")
    if not os.path.isfile(edited):
        sys.exit("no edited.ab; run 'edit' first")
    adb.restore(edited, app_id(cfg))
    log = adb.last_restore_log()
    if adb.restore_ok(log):
        print("restore reported success (verify with 'verify')")
    else:
        print("restore did NOT report success; check log:")
        print(log[-2000:])


def cmd_verify(cfg):
    latest = latest_fetch(cfg["app"]["id"])
    if not latest:
        sys.exit("no fetch yet; run 'fetch' first")
    edited = os.path.join(latest, "edited.ab")
    if not os.path.isfile(edited):
        sys.exit("no edited.ab; run 'edit' first")
    print(f"verifying {edited} is self-consistent (decode -> re-encode -> decode):")
    cfg_file = os.path.join(CONFIG_DIR, f"{cfg['app']['name']}.json")
    diff_js = os.path.join(REPO_ROOT, "src", "cli", "diff.js")
    import tempfile
    with tempfile.TemporaryDirectory(prefix="abctl_verify_") as tmp:
        r = run_node([diff_js, edited, edited, cfg_file, tmp])
        print(r.stdout or r.stderr)
        if r.returncode != 0:
            sys.exit("verify failed")
    print("TIP: for on-device verification, fetch again after opening the game "
          "and run: abctl diff <latest>/source.ab <latest>/edited.ab")


def cmd_diff(cfg, a, b):
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="abctl_diff_")
    cfg_file = os.path.join(CONFIG_DIR, f"{cfg['app']['name']}.json")
    diff_js = os.path.join(REPO_ROOT, "src", "cli", "diff.js")
    r = run_node([diff_js, a, b, cfg_file, tmpdir])
    print(r.stdout or r.stderr)
    if r.returncode != 0:
        sys.exit("diff failed")


def main(argv=None):
    p = argparse.ArgumentParser(prog="abctl")
    p.add_argument("command", choices=["fetch", "edit", "push", "verify", "diff"])
    p.add_argument("app", nargs="?", default=None)
    p.add_argument("patch", nargs="?", default=None)
    p.add_argument("--set", action="append", default=[], dest="set")
    p.add_argument("--add-item", type=int, action="append", default=[], dest="add_item")
    p.add_argument("--del-item", type=int, action="append", default=[], dest="del_item")
    p.add_argument("files", nargs="*")
    args = p.parse_args(argv)

    if args.command == "diff":
        positional = [x for x in (args.files + [args.app, args.patch]) if x]
        ab_files = [x for x in positional if x.lower().endswith(".ab")]
        if len(ab_files) != 2:
            sys.exit("usage: abctl diff <a.ab> <b.ab> [app]")
        cfg_name = next((x for x in positional if not x.lower().endswith(".ab")), "nadia")
        cmd_diff(load_cfg(cfg_name), ab_files[0], ab_files[1])
        return

    cfg = load_cfg(args.app or "nadia")
    if args.command == "fetch":
        cmd_fetch(cfg)
    elif args.command == "edit":
        if not args.patch:
            args.patch = os.path.join(PATCH_DIR, "full-set.json")
        elif not os.path.isabs(args.patch):
            args.patch = os.path.join(os.getcwd(), args.patch)
        cmd_edit(cfg, args.patch, args)
    elif args.command == "push":
        cmd_push(cfg)
    elif args.command == "verify":
        cmd_verify(cfg)


if __name__ == "__main__":
    main()
