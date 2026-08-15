"""Android backup (.ab) container read/write.

Format:
    magic  "ANDROID BACKUP"
    version (e.g. "5")
    compression flag ("1" = deflate, "none" = uncompressed)
    ...optional fields...
    "none\\n"     <- terminator before the payload
    payload      (tar, optionally zlib-deflated)

Only the deflate (version 5, "1") case is implemented here, which is what
adb produces on modern devices for unencrypted backups.
"""

import io
import os
import tarfile
import zlib

MAGIC = b"ANDROID BACKUP"
MAGIC_LEN = len(MAGIC)

class AbError(Exception):
    pass


def read_payload(path: str) -> bytes:
    """Read an .ab file and return the decompressed tar bytes."""
    data = open(path, "rb").read()
    if not data.startswith(MAGIC):
        raise AbError(f"{path}: bad magic (not an Android backup)")
    lines = data[:MAGIC_LEN + 64].split(b"\n")
    # lines: [b'ANDROID BACKUP', b'5', b'1', b'none', ...]
    version = lines[1] if len(lines) > 1 else b""
    compression = lines[2] if len(lines) > 2 else b""
    idx = data.index(b"none\n") + len(b"none\n")
    payload = data[idx:]
    if version == b"5" and compression == b"1":
        return zlib.decompress(payload)
    if compression == b"none":
        return payload
    raise AbError(f"{path}: unsupported backup encoding (version={version!r} compression={compression!r})")


def write_payload(tar_bytes: bytes, out_path: str, compress_level: int = 9) -> int:
    """Write tar bytes as a version-5 deflate .ab file. Returns file size."""
    header = b"ANDROID BACKUP\n5\n1\nnone\n"
    ab = header + zlib.compress(tar_bytes, compress_level)
    with open(out_path, "wb") as f:
        f.write(ab)
    return len(ab)


def list_members(path: str):
    """Return list of tarfile.TarInfo members from an .ab file."""
    tf = tarfile.open(fileobj=io.BytesIO(read_payload(path)), mode="r:")
    members = tf.getmembers()
    tf.close()
    return members


def validate_semantic_paths(members) -> list[str]:
    """Return member names the Android parser would reject (empty = OK).

    Mirrors TarBackupReader logic after stripping the "apps/" prefix:
      * no slash at all -> "Illegal semantic path" (bare "apps/<pkg>")
      * remainder is "_manifest"/"_meta" -> valid, terminal
      * otherwise a second slash must exist to split the domain ->
        "apps/<pkg>/<domain>" alone is illegal (""Illegal semantic path
        in non-manifest <domain>")
    """
    bad = []
    for m in members:
        p = m.name
        if not p.startswith("apps/"):
            continue
        rest = p[len("apps/"):]
        slash1 = rest.find("/")
        if slash1 < 0:
            bad.append(p)
            continue
        remainder = rest[slash1 + 1:]
        if remainder in ("_manifest", "_meta"):
            continue
        if "/" not in remainder:
            bad.append(p)
    return bad
