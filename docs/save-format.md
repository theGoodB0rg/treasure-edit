# Treasure of Nadia save format

## Where the save lives

The game (RPG Maker MV running in a WebView) stores its state in the WebView's
Local Storage leveldb:

```
apps/nlt.media.treasure/r/app_webview/Default/Local Storage/leveldb/
```

Keys inside the leveldb:

| key (hex)                  | meaning |
|---|---|
| `5f66696c653a2f2f00015250472046696c6531` (`_file://\0\x01RPG File1`) | slot 1 save |
| `5f66696c653a2f2f000152504720476c6f62616c` (`_file://\0\x01RPG Global`) | global save (playtime, timestamps) |

## Encoding layers

1. **leveldb value**: first byte is the leveldb "type" byte `0x01`
   (string), followed by an LZString base64 payload (decoded as latin1).
2. **LZString**: the game's own variant — `src/codec/lz_string.js` is
   vendored from the APK's `apk_lz_string.js` and must match exactly.
3. **JSON**: `JSON.parse` of the decompressed string yields the RPGM save
   object with JsonEx annotations.

## JsonEx annotations

```
"$PVBase": ...
"$gameParty": { "@c": 123, "@a": { "_gold": 100000, "_items": { "@a": {...}, "@c": 752 } } }
```

- `@a` is the real object/array.
- `@c` is a circular-reference ID — never edit it.
- Edit field values through `@a` (e.g. `@a._gold`).

The decoder/encoder in `src/codec/rpgmv.js` preserves `@c` and edits `@a`.
Roundtrip is verified by `tests/test_codec.js`.

## Field maps (`config/nadia.json`)

### money
Sets `$gameParty._gold` and the currency mirrors:
- `variables[2]` = raw amount
- `variables[51]` = formatted string `"$100,000,000"`
- `variables[208]` = `_gold`
- `variables[353]` = `_gold` (some builds)

### moan (sneak-peek toggle)
- `variables[3]` = 4

### kamasutra "all"
Unlocks all 54 pages:
- 54 page switches flipped ON (config `kamasutra.pages` list)
- girl vars 82–93 set to 5
- totals: `variables[496] = 60`, `variables[363] = 60`, `variables[81] = 60`
- `variables[263] = "60/60"`

### items
Sets presence count = 1 for:
- 8 story items (config `items.story` keys 19, 27, 38, 46, 56, 136, 268, 311)
- 18 lures (keys 95–112)
- 12 torn pages (keys 318–329)

The patch only adds keys that are absent; existing values are left alone.

## Patches are data

`patches/full-set.json`:

```json
{
  "money": 100000000,
  "moan": true,
  "kamasutra": "all",
  "items": ["all"]
}
```

`--set`/`--add-item`/`--del-item` on the CLI override values without touching
any code:

```bash
python abctl.py edit nadia patches/full-set.json --set money=50000000
```
