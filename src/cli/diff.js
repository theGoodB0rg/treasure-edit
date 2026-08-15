'use strict';
// diff.js <a.ab> <b.ab> <config.json> — decode slot-1 JSON from two backups
// and print before/after for the fields the model knows about.
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const tar = require('tar');
const { ClassicLevel } = require('classic-level');

const rpgmv = require('../codec/rpgmv.js');

function die(msg) {
  console.error('diff: ' + msg);
  process.exit(1);
}

(async () => {
  const [a, b, cfgFile, tmpDir] = process.argv.slice(2);
  if (!a || !b || !cfgFile || !tmpDir) die('usage: diff.js <a.ab> <b.ab> <config.json> <tmpdir>');
  const cfg = JSON.parse(fs.readFileSync(cfgFile, 'utf8'));
  const slotKey = Buffer.from(cfg.leveldb.slot1_key, 'hex');

  async function slotOf(ab) {
    const data = fs.readFileSync(ab);
    const idx = data.indexOf(Buffer.from('none\n')) + 5;
    const tarBytes = zlib.inflateSync(data.subarray(idx));
    const root = path.join(tmpDir, path.basename(ab, '.ab'));
    fs.mkdirSync(root, { recursive: true });
    const tarFile = path.join(root, 'inner.tar');
    fs.writeFileSync(tarFile, tarBytes);
    await tar.extract({ file: tarFile, cwd: root });
    const ldbDir = path.join(root, cfg.leveldb.rel_path);
    const db = new ClassicLevel(ldbDir, { keyEncoding: 'buffer', valueEncoding: 'buffer', readOnly: true });
    await db.open();
    const val = await db.get(slotKey);
    await db.close();
    return rpgmv.decodeSave(val);
  }

  const [sa, sb] = await Promise.all([slotOf(a), slotOf(b)]);
  const fields = ['_gold', '_items'];
  const vIdx = [2, 3, 51, 208, 263, 353, 363, 496];
  const out = {};
  for (const f of fields) {
    if (JSON.stringify(sa.party[f]) !== JSON.stringify(sb.party[f])) {
      out['party.' + f] = { before: sa.party[f], after: sb.party[f] };
    }
  }
  const va = rpgmv.variables(sa), vb = rpgmv.variables(sb);
  for (const i of vIdx) {
    if (JSON.stringify(va[i]) !== JSON.stringify(vb[i])) {
      out['var[' + i + ']'] = { before: va[i], after: vb[i] };
    }
  }
  console.log(JSON.stringify(out, null, 2));
})().catch((e) => { console.error('diff: ERROR ' + (e && e.stack ? e.stack : e)); process.exit(1); });
