'use strict';
// leveldb read/write for the WebView Local Storage database.
const { ClassicLevel } = require('classic-level');

async function openDir(dir, { readOnly = false } = {}) {
  const db = new ClassicLevel(dir, {
    keyEncoding: 'buffer',
    valueEncoding: 'buffer',
    readOnly,
  });
  await db.open();
  return db;
}

async function readAll(db) {
  const map = new Map();
  for await (const [key, value] of db.iterator()) {
    map.set(key.toString('hex'), value);
  }
  return map;
}

async function writeAll(db, entries) {
  for (const [keyHex, value] of entries) {
    await db.put(Buffer.from(keyHex, 'hex'), value);
  }
}

module.exports = { openDir, readAll, writeAll };
