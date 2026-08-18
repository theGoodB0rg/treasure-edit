'use strict';
// Semantic patch model for Treasure of Nadia saves.
//
// A patch is DATA, not code:
//   { "money": 100000000, "moan": 4, "kamasutra": "all", "items": [...ids] }
// The model resolves each semantic key into concrete writes on the save
// object (party fields + JsonEx @a variable/switch arrays). Changing a value
// later means editing the patch JSON, not this code.

const rpgmv = require('../codec/rpgmv.js');

function toLocaleMoney(n) {
  return '$' + Number(n).toLocaleString('en-US');
}

function apply(patch, save, cfg) {
  const vars = rpgmv.variables(save);
  const sw = rpgmv.switches(save);

  if (patch.money !== undefined) {
    const value = Number(patch.money);
    save.party._gold = value;
    for (const id of cfg.fields.money.variables) {
      vars[id] = value;
    }
    // var[51] is the HUD money string ("$100,000,000").
    vars[51] = toLocaleMoney(value);
  }

  if (patch.moan !== undefined) {
    for (const id of cfg.fields.moan.variables) {
      vars[id] = Number(patch.moan);
    }
  }

  if (patch.kamasutra === 'all') {
    const ks = cfg.kamasutra;
    for (const id of ks.page_switches) {
      sw[id] = true;
    }
    for (const id of ks.girl_variables) {
      vars[id] = ks.pages_per_girl;
    }
    for (const id of cfg.fields.kamasutra_total.variables) {
      vars[id] = ks.total_pages;
    }
    vars[cfg.fields.kamasutra_total.status_variable] =
      `${ks.total_pages}/${ks.total_pages}`;
  }

  if (Array.isArray(patch.items)) {
    for (const id of patch.items) {
      const k = String(id);
      if (!save.party._items[k] || save.party._items[k] < 1) {
        save.party._items[k] = 1;
      }
    }
  }

  if (patch.item_quantities && typeof patch.item_quantities === 'object') {
    for (const [id, qty] of Object.entries(patch.item_quantities)) {
      save.party._items[String(id)] = Number(qty);
    }
  }

  if (patch.switches && typeof patch.switches === 'object') {
    for (const [id, val] of Object.entries(patch.switches)) {
      sw[Number(id)] = !!val;
    }
  }

  if (patch.variables && typeof patch.variables === 'object') {
    for (const [id, val] of Object.entries(patch.variables)) {
      vars[Number(id)] = val;
    }
  }

  return save;
}

module.exports = { apply };
