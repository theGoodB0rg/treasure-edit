"""Rebuild a backup .ab by copying the genuine tar member-by-member.

Why this matters: a naive re-tar (walking an extracted tree) emits bare
top-level directory entries (``apps``, ``apps/<pkg>``, ``apps/<pkg>/<domain>``)
which Android's restore parser rejects with ``Illegal semantic path in ...``,
aborting the whole restore. The genuine tar produced by adb only contains
entries with >= 3 path segments below ``apps/``.

The reliable approach is therefore: keep every original member byte-identical
(name, type, mode, uid/gid, mtime, payload) and swap ONLY the leveldb subtree
with our modified files. This is the rebuild that finally restored cleanly
("Full restore pass complete" + verified data on device).
"""

import io
import os
import tarfile
import zlib

from .ab import read_payload, write_payload, validate_semantic_paths

# Default ownership/metadata observed on the genuine leveldb members.
DEFAULT_UID = 10428
DEFAULT_GID = 10428
DEFAULT_MODE_FILE = 0o600
DEFAULT_MODE_DIR = 0o700
DEFAULT_MTIME = 1786776089


def _copy_member(tar: tarfile.TarFile, src: tarfile.TarFile, member: tarfile.TarInfo):
    """Write a byte-faithful copy of member from src into tar."""
    ti = tarfile.TarInfo(member.name)
    ti.type = member.type
    ti.mode = member.mode
    ti.uid = member.uid
    ti.gid = member.gid
    ti.uname = member.uname
    ti.gname = member.gname
    ti.mtime = member.mtime
    ti.size = member.size
    if member.isreg():
        fh = src.extractfile(member)
        tar.addfile(ti, fh)
        if fh:
            fh.close()
    else:
        tar.addfile(ti)


def _mod_ldb_files(mod_dir: str) -> list[str]:
    """The files in the modified leveldb dir. LevelDB file names are
    auto-generated (000003.log / 000005.ldb / MANIFEST-000002 ...) and do not
    matter to the game -- it resolves the layout via CURRENT/MANIFEST. So we
    copy whatever classic-level produced rather than assuming fixed names."""
    names = sorted(f for f in os.listdir(mod_dir) if os.path.isfile(os.path.join(mod_dir, f)))
    if not names:
        raise FileNotFoundError(f"modified leveldb dir is empty: {mod_dir}")
    if "CURRENT" not in names or "MANIFEST" not in " ".join(names):
        raise ValueError(f"modified leveldb dir missing CURRENT/MANIFEST: {mod_dir}")
    return names


def _add_mod_ldb(tar: tarfile.TarFile, mod_dir: str, ldb_rel: str,
                 files: list[str] | None, uid: int, gid: int):
    if files is None:
        files = _mod_ldb_files(mod_dir)
    for name in files:
        p = os.path.join(mod_dir, name)
        if not os.path.isfile(p):
            raise FileNotFoundError(f"modified leveldb file missing: {p}")
        ti = tarfile.TarInfo(ldb_rel + "/" + name)
        ti.type = tarfile.REGTYPE
        ti.mode = DEFAULT_MODE_FILE
        ti.uid = uid
        ti.gid = gid
        ti.uname = ""
        ti.gname = ""
        ti.mtime = DEFAULT_MTIME
        ti.size = os.path.getsize(p)
        with open(p, "rb") as fh:
            tar.addfile(ti, fh)


def rebuild(genuine_ab: str, mod_ldb_dir: str, ldb_rel: str,
            ldb_files: list[str] | None = None, out_tar: str | None = None) -> bytes:
    """Build a new tar with genuine members + swapped leveldb subtree.

    ldb_files defaults to "everything in mod_ldb_dir" (file names are
    leveldb-internal). Returns the tar bytes; if out_tar is given the tar is
    also written there.
    """
    src_bytes = read_payload(genuine_ab)
    src = tarfile.open(fileobj=io.BytesIO(src_bytes), mode="r:")

    if ldb_files is None:
        ldb_files = _mod_ldb_files(mod_ldb_dir)

    buf = io.BytesIO()
    out = tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT)
    ldb_prefix = ldb_rel + "/"
    count = 0
    for member in src.getmembers():
        if member.name == ldb_rel:
            _copy_member(out, src, member)
            _add_mod_ldb(out, mod_ldb_dir, ldb_rel, ldb_files, DEFAULT_UID, DEFAULT_GID)
            count += 1 + len(ldb_files)
            continue
        if member.name.startswith(ldb_prefix):
            continue  # drop original leveldb members, replaced above
        _copy_member(out, src, member)
        count += 1
    src.close()
    out.close()

    tar_bytes = buf.getvalue()

    # Safety net: the rebuilt tar must not contain parser-rejecting paths.
    tf = tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:")
    bad = validate_semantic_paths(tf.getmembers())
    tf.close()
    if bad:
        raise ValueError(f"rebuild produced illegal semantic paths: {bad}")

    if out_tar:
        with open(out_tar, "wb") as f:
            f.write(tar_bytes)
    return tar_bytes


def rebuild_to_ab(genuine_ab: str, mod_ldb_dir: str, ldb_rel: str,
                  out_ab: str, ldb_files: list[str] | None = None,
                  compress_level: int = 9) -> int:
    """Rebuild and write a new .ab file. Returns file size."""
    tar_bytes = rebuild(genuine_ab, mod_ldb_dir, ldb_rel, ldb_files)
    return write_payload(tar_bytes, out_ab, compress_level)
