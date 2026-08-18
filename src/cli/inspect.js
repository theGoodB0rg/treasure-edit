'use strict';
// Inspect a Treasure of Nadia save: dump items, switches, variables.
// Usage: node src/cli/inspect.js <leveldb-dir> <config.json>

const fs = require('fs');
const { ClassicLevel } = require('classic-level');
const rpgmv = require('../codec/rpgmv.js');
const { readAll } = require('../storage/ldb.js');

function die(msg) {
  console.error('inspect: ' + msg);
  process.exit(1);
}

(async () => {
  const [ldbDir, cfgFile] = process.argv.slice(2);
  if (!ldbDir || !cfgFile) {
    die('usage: inspect.js <leveldb-dir> <config.json>');
  }

  const cfg = JSON.parse(fs.readFileSync(cfgFile, 'utf8'));
  const db = new ClassicLevel(ldbDir, { keyEncoding: 'buffer', valueEncoding: 'buffer', readOnly: true });
  await db.open();
  const entries = await readAll(db);
  await db.close();

  const slotKey = cfg.leveldb.slot1_key;
  if (!entries.has(slotKey)) {
    die('slot 1 key not in leveldb');
  }

  const save = rpgmv.decodeSave(entries.get(slotKey));
  const vars = rpgmv.variables(save);
  const sw = rpgmv.switches(save);

  // --- Items ---
  const items = save.party._items;
  const itemIds = Object.keys(items)
    .filter(k => k !== '@c')
    .map(k => ({ id: Number(k), qty: items[k] }))
    .sort((a, b) => a.id - b.id);

  console.log('=== ITEMS IN INVENTORY ===');
  console.log('Total item types:', itemIds.length);
  console.log(JSON.stringify(itemIds, null, 2));

  // --- Variables (non-zero only) ---
  const nonZeroVars = [];
  for (let i = 0; i < vars.length; i++) {
    if (vars[i] !== undefined && vars[i] !== null && vars[i] !== 0 && vars[i] !== '') {
      nonZeroVars.push({ id: i, value: vars[i] });
    }
  }
  console.log('\n=== VARIABLES (non-zero) ===');
  console.log('Total non-zero:', nonZeroVars.length);
  console.log(JSON.stringify(nonZeroVars, null, 2));

  // --- Switches (true only) ---
  const trueSwitches = [];
  for (let i = 0; i < sw.length; i++) {
    if (sw[i] === true) {
      trueSwitches.push(i);
    }
  }
  console.log('\n=== SWITCHES (true) ===');
  console.log('Total true:', trueSwitches.length);
  console.log(JSON.stringify(trueSwitches));

  // --- Party state ---
  console.log('\n=== PARTY STATE ===');
  console.log(JSON.stringify({
    gold: save.party._gold,
    itemTypes: Object.keys(save.party._items).filter(k => k !== '@c').length,
    weapons: Object.keys(save.party._weapons || {}).filter(k => k !== '@c').length,
    armors: Object.keys(save.party._armors || {}).filter(k => k !== '@c').length,
  }, null, 2));

  // --- Known config fields ---
  console.log('\n=== KNOWN CONFIG FIELDS ===');
  const knownVars = cfg.fields.money.variables;
  const knownMoney = {
    party_gold: save.party._gold,
    vars: knownVars.map(id => ({ id, value: vars[id] })),
  };
  console.log('Money:', JSON.stringify(knownMoney, null, 2));

  // --- Game version hint (variable 496 is version) ---
  console.log('Version var (496):', vars[496]);
  console.log('Moan var (3):', vars[3]);
  console.log('Kamasutra status (263):', vars[263]);
})();
