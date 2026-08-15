'use strict';
// Node side of the pipeline. Usage:
//   node src/cli/apply_patch.js <in-leveldb-dir> <out-leveldb-dir> <patch.json> <config.json>
//
// Reads every key of the source leveldb, decodes slot 1 (the RPGMV save),
// applies the semantic patch, re-encodes slot 1, writes the full key set
// to a NEW leveldb directory. All other keys are copied verbatim.
//
// stdout (last line, JSON): { "ok": true, "before": {...}, "after": {...} }

const fs = require('fs');
const path = require('path');
const { ClassicLevel } = require('classic-level');
const rpgmv = require('../codec/rpgmv.js');
const model = require('../model/nadia.js');
const { readAll, writeAll } = require('../storage/ldb.js');

function die(msg) {
  console.error('apply_patch: ' + msg);
  process.exit(1);
}

function summary(save, cfg) {
  const vars = rpgmv.variables(save);
  const sw = rpgmv.switches(save);
  const girls = cfg.kamasutra.girl_variables;
  const pages = girls.reduce((s, g) => s + (vars[g] || 0), 0);
  const itemCount = Object.keys(save.party._items).filter((k) => k !== '@c').length;
  return {
    gold: save.party._gold,
    var2: vars[2],
    var51: vars[51],
    var3: vars[3],
    var208: vars[208],
    var353: vars[353],
    pages,
    var496: vars[496],
    var363: vars[363],
    var263: vars[263],
    switchesOn: cfg.kamasutra.page_switches.filter((s) => sw[s]).length,
    items: itemCount,
  };
}

(async () => {
  const [inDir, outDir, patchFile, cfgFile] = process.argv.slice(2);
  if (!inDir || !outDir || !patchFile || !cfgFile) {
    die('usage: apply_patch.js <in-ldb> <out-ldb> <patch.json> <config.json>');
  }
  const patch = JSON.parse(fs.readFileSync(patchFile, 'utf8'));
  const cfg = JSON.parse(fs.readFileSync(cfgFile, 'utf8'));

  const db = new ClassicLevel(inDir, { keyEncoding: 'buffer', valueEncoding: 'buffer' });
  await db.open();
  const entries = await readAll(db);
  await db.close();

  const slotKey = Buffer.from(cfg.leveldb.slot1_key, 'hex');
  const slotHex = slotKey.toString('hex');
  if (!entries.has(slotHex)) {
    die(`slot 1 key not present in leveldb: ${cfg.leveldb.slot1_key}`);
  }

  const save = rpgmv.decodeSave(entries.get(slotHex));
  const before = summary(save, cfg);

  model.apply(patch, save, cfg);

  const after = summary(save, cfg);
  entries.set(slotHex, rpgmv.encodeSave(save));

  if (fs.existsSync(outDir)) {
    fs.rmSync(outDir, { recursive: true, force: true });
  }
  fs.mkdirSync(outDir, { recursive: true });
  const out = new ClassicLevel(outDir, { keyEncoding: 'buffer', valueEncoding: 'buffer' });
  await out.open();
  await writeAll(out, entries);
  await out.close();

  console.log(JSON.stringify({ ok: true, before, after }));
})().catch((e) => {
  console.error('apply_patch: ERROR ' + (e && e.stack ? e.stack : e));
  process.exit(1);
});
