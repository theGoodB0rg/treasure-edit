# treasure-edit

## Skip the grind. Keep the game.

Give yourself the save you'd already earned the right to — **no root, no debug
APK, no emulator**. Just `adb backup` and a script.

| | before | after |
|---|---|---|
| gold | $20,280 | **$100,000,000** |
| kamasutra pages | 0/60 | **60/60** |
| items | 8 | **43** |

Works on a stock, locked-down Android phone (tested on Realme/OPPO, not
Android 16-specific). Vendor backup behavior may vary by brand — see the
caveats below.

## Why this exists

I wanted to play the game, not spend evenings grinding for late-game content
items and pages. Real life exists. So I edited the save instead.

It started small: cash. Then it grew — found items, story items, kamasutra
pages, the whole late-game data set. And that's when the fun started: **the
phone started silently refusing my restores.**

## The wall

`adb restore` would say:

```
Full restore pass complete.
```

...and change nothing. No error. No warning. The save was untouched.

The culprit turned out to be a subtle tar-structure rule in Android's own
restore parser (`TarBackupReader`). A naive re-tar emits bare directory
entries — `apps`, `apps/<pkg>`, `apps/<pkg>/<domain>` — and the parser throws
`Illegal semantic path` on each one, then quietly writes nothing. The device
wasn't broken; my archive was.

The fix is now encoded in code **and** a test that reproduces the parser's
logic, so a bad archive never slips through again. Details in
`docs/pipeline.md`.

## How it works

RPG Maker MV games run as HTML5 in a WebView. The "save file" isn't a file —
it's the WebView's localStorage, a LevelDB under
`app_webview/.../Default/Local Storage/leveldb/`.

```
adb backup          -> .ab (deflate(tar))
    -> leveldb dir  -> key "_file://RPG File1"
        -> LZString decompress (the game's custom variant)
            -> RPGM JsonEx JSON  { "@c": <ref id>, "@a": [real array] }
                -> patch: edit "@a", leave "@c" alone
        -> re-encode -> new leveldb dir
    -> faithful rebuild (byte-faithful member copy + swapped subtree)
adb restore         -> done
```

Key discovery: **`adb backup`/`restore` works without root or a debug build**
on modern Android. Backup needs the app running; restore needs it
force-stopped and you pressing "Restore my data" on the device. Never kill
`com.android.backupconfirm`. `pm clear` is blocked on some ROMs — a full wipe
is a Settings → Apps → Clear data job.

## Quickstart

```bash
pip install pytest
npm install

# 1. Pull the current save off the device (app must be RUNNING)
python abctl.py fetch nadia

# 2. Build an edited .ab
python abctl.py edit nadia patches/full-set.json

# 3. Push it (app gets force-stopped; YOU press "Restore my data")
python abctl.py push nadia

# 4. Open the game, confirm, save in-game.
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
| `verify`| decode → re-encode → decode the edited `.ab`; re-fetch guidance |
| `diff`  | `abctl.py diff <a.ab> <b.ab>` → field-level before/after |

## Other RPGM MV games?

The game-specific parts are one config file (`config/nadia.json`: package id,
leveldb path, key layout, field maps) and one patch (`patches/full-set.json`).
Same engine, same storage pattern — if your WebView/localStorage RPGM MV game
stores saves the same way, support is one JSON file away. PRs welcome.

## Layout

```
config/nadia.json            app manifest (package id, leveldb path, field maps)
patches/full-set.json        data-driven edit values
src/container/               python: .ab read/write, faithful tar rebuild, adb
src/codec/                   node: LZString + JsonEx (@a/@c) encode/decode
src/storage/                 node: classic-level read/copy/write
src/model/                   node: semantic patch resolution (money/kamasutra/items)
src/cli/                     abctl entry point + apply_patch.js + diff.js
tests/                       pytest + node codec roundtrip + golden fixtures
fixtures/                    genuine backup + the known-good edited backup
```

## Caveats & hard-won rules

1. **Tar structure** — a naive re-tar breaks restores ("Illegal semantic
   path"); the rebuild copies genuine members verbatim and swaps only the
   leveldb subtree. Regression-tested.
2. **backup needs the app RUNNING**; a stopped app produces an empty archive.
3. **restore needs the app FORCE-STOPPED** + screen awake; you press "Restore
   my data". Never kill `com.android.backupconfirm`.
4. **"Full restore pass complete" is not proof** — verify by re-fetching and
   diffing.
5. **`pm clear` is blocked on this ROM** (`CLEAR_APP_USER_DATA`); a full wipe
   is Settings → Apps → ... → Storage → Clear data.
6. **JsonEx `@c`/`@a`**: `@a` is the real array, `@c` is a circular-ref ID.
   Edit `@a`, never touch `@c`.
7. **LZString variant** — the game uses its own LZString build; we depend on
   the `lz-string` npm package and verify it with a byte-faithful roundtrip
   test against the genuine fixture.

## Tests

```
pytest                      # 8 tests: tar guard, semantic paths, patch E2E
node tests/test_codec.js    # decode → re-encode → decode stability on real save
```

Golden fixtures: a genuine backup and the known-good edited backup, so the
whole pipeline is verifiable without a device.

## License

MIT. See `LICENSE`.
