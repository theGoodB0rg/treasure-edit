'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const tar = require('tar');
const { ClassicLevel } = require('classic-level');

const rpgmv = require('../src/codec/rpgmv.js');

const REPO = path.join(__dirname, '..');
const GENUINE = path.join(REPO, 'fixtures', 'genuine_playback.ab');
const CONFIG = JSON.parse(fs.readFileSync(path.join(REPO, 'config', 'nadia.json'), 'utf8'));
const TMP = fs.mkdtempSync(path.join(require('os').tmpdir(), 'treasure_codec_'));

async function extractLeveldb(abPath, outRoot) {
  const data = fs.readFileSync(abPath);
  const idx = data.indexOf(Buffer.from('none\n')) + 5;
  fs.mkdirSync(outRoot, { recursive: true });
  const tarFile = path.join(outRoot, 'inner.tar');
  fs.writeFileSync(tarFile, zlib.inflateSync(data.subarray(idx)));
  await tar.extract({ file: tarFile, cwd: outRoot });
  return path.join(outRoot, CONFIG.leveldb.rel_path);
}

async function main() {
  const ldbDir = await extractLeveldb(GENUINE, path.join(TMP, 'genuine'));
  const db = new ClassicLevel(ldbDir, { keyEncoding: 'buffer', valueEncoding: 'buffer', readOnly: true });
  await db.open();
  const slot = Buffer.from(CONFIG.leveldb.slot1_key, 'hex');
  const val = await db.get(slot);
  await db.close();

  // decode -> re-encode -> decode must be stable
  const save = rpgmv.decodeSave(val);
  const encoded = rpgmv.encodeSave(save);
  const save2 = rpgmv.decodeSave(encoded);
  assert.deepStrictEqual(save, save2, 'roundtrip not stable');

  // JsonEx accessors work
  const vars = rpgmv.variables(save);
  assert.strictEqual(typeof vars[2], 'number', 'var2 should be a number');
  const sw = rpgmv.switches(save);
  assert.ok(Array.isArray(sw), 'switches should be an array');

  console.log('codec roundtrip OK; slot1 decoded size:', JSON.stringify(save).length);
}

main().catch((e) => { console.error(e); process.exit(1); });
