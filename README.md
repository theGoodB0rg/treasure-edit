# treasure-edit

Toolchain to pull an Android app's backup (`.ab`), edit its WebView
Local Storage save, and push it back. Built for **Treasure of Nadia**
(RPG Maker MV running in a WebView), architected so other RPGM/WebView
apps are just a new `config/<app>.json`.

## Why this repo exists

The pipeline was originally a pile of one-off scripts. The important
discoveries — the adb quirks, the tar structure the Android restore parser
requires, the RPGM save encoding — are now code + tests + docs so they are
never rediscovered.

## Layout

```
config/nadia.json            app manifest (package id, leveldb path, field maps)
patches/full-set.json        DATA-driven edit values
src/container/               python: .ab read/write, faithful tar rebuild, adb
src/codec/                   node: LZString + JsonEx (@a/@c) encode/decode
src/storage/                 node: classic-level read/copy/write
src/model/                   node: semantic patch resolution (money/kamasutra/items)
src/cli/                     abctl entry point + apply_patch.js + diff.js
tests/                       pytest + node codec roundtrip + golden fixtures
fixtures/                    genuine backup + the known-good edited backup
```

## Quickstart

```bash
pip install pytest
npm install

# 1. Pull the current save off the device
python abctl.py fetch nadia
#    -> opens backup dialog; app must be RUNNING

# 2. Build an edited .ab
python abctl.py edit nadia patches/full-set.json
#    -> work/nlt.media.treasure/<latest>/edited.ab

# 3. Push it (app gets force-stopped; YOU press "Restore my data")
python abctl.py push nadia

# 4. Open the game, confirm the values, then save in-game.
```

Changing values later is **config, not code**:

```bash
python abctl.py edit nadia patches/full-set.json --set money=50000000
python abctl.py edit nadia patches/full-set.json --set money=75000000 --add-item 19
```

## Commands

| command | purpose |
|---|---|
| `fetch` | `adb backup` the app (must be running), extract leveldb |
| `edit`  | apply patch (+ optional `--set`/`--add-item`/`--del-item`) → new `.ab` |
| `push`  | force-stop app, `adb restore`, report logcat result |
| `verify`| guidance to re-fetch and diff after a manual in-game check |
| `diff`  | `abctl.py diff <a.ab> <b.ab>` → field-level before/after |

## Hard-won rules (all encoded in code/tests)

1. **Tar structure**: a naive re-tar emits bare dir entries (`apps`,
   `apps/<pkg>`, `apps/<pkg>/<domain>`) which Android rejects with
   "Illegal semantic path" and the restore silently writes nothing.
   We rebuild by copying genuine members verbatim and swapping only the
   leveldb subtree. See `src/container/rebuild.py` + `test_container.py`.
2. **backup needs the app RUNNING**; a stopped app produces an empty archive.
3. **restore needs the app FORCE-STOPPED** and the screen awake; you press
   "Restore my data". Never kill `com.android.backupconfirm`.
4. **"Full restore pass complete" in logcat is not proof** — verify by
   re-fetching and decoding (that's what `diff`/`verify` are for).
5. **`pm clear` is blocked on this ROM** (no `CLEAR_APP_USER_DATA`). A full
   data wipe is only possible via Settings → Apps → ... → Storage → Clear data.
6. **JsonEx `@c`/`@a`**: `@a` is the real array, `@c` is a circular-ref ID.
   Edit through `@a`, never touch `@c`.
7. **LZString variant must match the game** — see `src/codec/lz_string.js`
   (vendored from the app's own JS) and the roundtrip test.

See `docs/pipeline.md` and `docs/save-format.md` for the full detail.
