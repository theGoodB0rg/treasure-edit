"""End-to-end: genuine .ab -> extract -> apply patch -> rebuild -> verify.

Runs the exact same code paths the CLI uses, against the fixtures.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from container import ab
from container.rebuild import rebuild_to_ab

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(REPO, "fixtures")
GENUINE = os.path.join(FIXTURES, "genuine_playback.ab")
KNOWN_GOOD = os.path.join(FIXTURES, "edited_working.ab")
PATCH = os.path.join(REPO, "patches", "full-set.json")
CONFIG = os.path.join(REPO, "config", "nadia.json")
APPLY_PATCH_JS = os.path.join(REPO, "src", "cli", "apply_patch.js")
LDB_REL = json.load(open(CONFIG, encoding="utf-8"))["leveldb"]["rel_path"]
NODE_PATH = os.path.join(REPO, "node_modules")


def extract_leveldb(ab_path, out_dir):
    tar_bytes = ab.read_payload(ab_path)
    tf = tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:")
    prefix = LDB_REL + "/"
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir)
    for m in tf.getmembers():
        if m.name == LDB_REL or m.name.startswith(prefix):
            rel = os.path.relpath(m.name, LDB_REL)
            if rel == ".":
                continue
            tgt = os.path.join(out_dir, rel)
            os.makedirs(os.path.dirname(tgt), exist_ok=True)
            if m.isreg():
                fh = tf.extractfile(m)
                with open(tgt, "wb") as f:
                    f.write(fh.read())
                fh.close()
            else:
                os.makedirs(tgt, exist_ok=True)
    tf.close()


def run_apply(in_dir, out_dir, patch_path):
    env = dict(os.environ)
    if NODE_PATH:
        env["NODE_PATH"] = NODE_PATH
    r = subprocess.run(
        ["node", APPLY_PATCH_JS, in_dir, out_dir, patch_path, CONFIG],
        capture_output=True, text=True, timeout=60, env=env,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_e2e_edit_matches_known_good(tmp_path):
    work = str(tmp_path)
    src_ldb = os.path.join(work, "ldb_orig")
    mod_ldb = os.path.join(work, "ldb_mod")
    extract_leveldb(GENUINE, src_ldb)
    result = run_apply(src_ldb, mod_ldb, PATCH)
    assert result["ok"] is True

    after = result["after"]
    assert after["gold"] == 100000000
    assert after["var2"] == 100000000
    assert after["var51"] == "$100,000,000"
    assert after["var3"] == 4
    assert after["var208"] == 100000000
    assert after["var353"] == 100000000
    assert after["pages"] == 60
    assert after["var496"] == 60
    assert after["var363"] == 60
    assert after["var263"] == "60/60"
    assert after["switchesOn"] == 54
    assert after["items"] == 43

    out_ab = os.path.join(work, "edited.ab")
    rebuild_to_ab(GENUINE, mod_ldb, LDB_REL, out_ab)
    assert ab.validate_semantic_paths(ab.list_members(out_ab)) == []


def test_override_money(tmp_path):
    work = str(tmp_path)
    src_ldb = os.path.join(work, "ldb_orig")
    mod_ldb = os.path.join(work, "ldb_mod")
    extract_leveldb(GENUINE, src_ldb)
    patch = json.load(open(PATCH, encoding="utf-8"))
    patch["money"] = 12345
    pf = os.path.join(work, "patch.json")
    json.dump(patch, open(pf, "w"))
    result = run_apply(src_ldb, mod_ldb, pf)
    assert result["after"]["gold"] == 12345
    assert result["after"]["var51"] == "$12,345"


def test_patch_is_stable_identity():
    """full-set.json must decode as valid JSON with the expected keys."""
    p = json.load(open(PATCH, encoding="utf-8"))
    assert set(p) == {"money", "moan", "kamasutra", "items"}
    assert p["kamasutra"] == "all"
    assert len(p["items"]) == 8 + 18 + 12
