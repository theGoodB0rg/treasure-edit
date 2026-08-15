# Pipeline & adb protocol notes

Everything here was discovered empirically on a Realme/OPPO Android device
(Google D2D backup transport active) while editing Treasure of Nadia. Treat
it as required knowledge for running the toolchain.

## The pipeline

```
adb backup              -> .ab (header + deflate(tar))
  |  zlib inflate
tar                     -> apps/<pkg>/r/app_webview/.../leveldb
  |  classic-level
leveldb keys            -> slot1 = RPGMV save JSON (LZString base64, value byte 0x01)
  |  LZString + JsonEx
save object             -> apply patch (money, kamasutra, items)
  |  reverse
leveldb_mod             -> classic-level dir (auto file names)
  |  faithful rebuild
new .ab                 -> adb restore
```

## adb quirks (this device)

| operation | requirement | why |
|---|---|---|
| `adb backup` | app **running** | a force-stopped app yields an empty/partial archive |
| `adb restore` | app **force-stopped**, screen awake | restore writes the tar over the app's data dir; a running app can fight it |
| restore confirm | user presses **"Restore my data"** | the UI is `com.android.backupconfirm`; do NOT kill it or the restore aborts |
| `pm clear` | **blocked** | `SecurityException: missing CLEAR_APP_USER_DATA`; only manual Settings → Clear data works |

Additional observations:

- Restore ran "Full restore pass complete" yet wrote **nothing** when the tar
  contained illegal paths. Success in logcat is necessary, not sufficient.
  Always verify by re-fetching + decoding.
- Waking the screen with `keyevent 224` can pop the OPPO search UI and steal
  focus from the backup/restore dialog; it also unlocks. The user just presses
  the button when it appears.
- `adb backup`/`restore` are deprecated but functional on this device.
  Header observed: `ANDROID BACKUP\n5\n1\nnone\n` (v5, deflate, unencrypted).

## Why a naive re-tar fails ("Illegal semantic path")

`TarBackupReader` strips the `apps/` prefix, then requires a slash after the
package name and (for non-manifest entries) a slash after the domain. A bare
directory entry `apps`, `apps/<pkg>`, or `apps/<pkg>/<domain>` fails:

```java
info.path = info.path.substring(APPS_PREFIX.length());
int slash = info.path.indexOf('/');
if (slash < 0) throw new IOException("Illegal semantic path in " + info.path);
...
slash = info.path.indexOf('/');
if (slash < 0) throw new IOException("Illegal semantic path in non-manifest " + info.path);
```

Our rebuild therefore copies genuine tar members **byte-for-byte** (order,
mode, uid/gid 10428, mtime) and only replaces the leveldb subtree with the
modified files. `validate_semantic_paths()` reproduces the parser check and is
run on every rebuild as a safety net.

## Rollback safety

Keep a fresh `adb backup` before every edit cycle. The fixtures directory has
a genuine backup and the last known-good edited backup; both are used by tests.

## Verify loop

After `push`, have the user open the game and confirm the values on screen,
then **save in-game** (a re-save of the loaded state preserves the edits).
The `diff` command compares two `.ab` files field-by-field for an automated
check.
