import io
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
EDITED = os.path.join(FIXTURES, "edited_working.ab")
LDB_REL = "apps/nlt.media.treasure/r/app_webview/Default/Local Storage/leveldb"


@pytest.fixture(scope="module")
def tmpwork(tmp_path_factory):
    return tmp_path_factory.mktemp("work")


def test_genuine_and_edited_have_valid_paths():
    for path in (GENUINE, EDITED):
        bad = ab.validate_semantic_paths(ab.list_members(path))
        assert bad == [], f"{path} has illegal semantic paths: {bad}"


def test_illegal_shallow_dir_is_caught():
    class Fake:
        name = "apps/nlt.media.treasure/r"
    bad = ab.validate_semantic_paths([Fake()])
    assert bad == ["apps/nlt.media.treasure/r"]


def test_manifest_and_meta_are_allowed():
    class Fake:
        name = "apps/nlt.media.treasure/_manifest"
    class Fake2:
        name = "apps/nlt.media.treasure/_meta"
    assert ab.validate_semantic_paths([Fake(), Fake2()]) == []


def test_rebuild_preserves_structure(tmpwork):
    # build a minimal mod leveldb dir (we just need CURRENT + MANIFEST + one file)
    mod = tmpwork / "ldb_mod"
    mod.mkdir()
    (mod / "CURRENT").write_bytes(b"MANIFEST-000002\n")
    (mod / "MANIFEST-000002").write_bytes(b"x")
    (mod / "000005.ldb").write_bytes(b"payload")
    out_ab = tmpwork / "edited.ab"
    size = rebuild_to_ab(GENUINE, str(mod), LDB_REL, str(out_ab))
    assert size > 0

    members = ab.list_members(str(out_ab))
    names = [m.name for m in members]
    # leveldb subtree fully replaced
    assert LDB_REL in names
    assert f"{LDB_REL}/000005.ldb" in names
    for old in ("000024.ldb", "000026.ldb", "000028.ldb", "000029.log"):
        assert f"{LDB_REL}/{old}" not in names
    # genuine entries still present
    assert "apps/nlt.media.treasure/_manifest" in names
    # nothing illegal
    assert ab.validate_semantic_paths(members) == []
    # no bare top-level dirs
    assert "apps" not in names and "apps/nlt.media.treasure" not in names


def test_missing_mod_dir_raises(tmpwork):
    with pytest.raises((FileNotFoundError, ValueError)):
        rebuild_to_ab(GENUINE, str(tmpwork / "nope"), LDB_REL, str(tmpwork / "x.ab"))
