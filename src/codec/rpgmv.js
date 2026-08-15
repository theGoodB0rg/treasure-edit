'use strict';
// Codec for RPG Maker MV WebView Local Storage values.
//
// Value layout: the leveldb value is a single leading "type" byte
// (0x01 = string) followed by an LZString base64 payload.
//
// The save JSON uses RPG Maker's JsonEx wire format: arrays are stored as
//   { "@c": <circular-ref id>, "@a": [ ... ] }
// "@c" is a *reference id* used to preserve object identity during
// serialize/deserialize, NOT a length gate. "@a" is the real array.
// Therefore edits must be applied through the "@a" arrays and "@c" must be
// left untouched.
const LZString = require('lz-string');

function decodeLevelValue(value) {
  if (!value || value.length < 2) {
    throw new Error('leveldb value too short');
  }
  if (value[0] !== 0x01) {
    throw new Error(`unexpected value type byte 0x${value[0].toString(16)} (expected 0x01 string)`);
  }
  const b64 = value.subarray(1).toString('latin1');
  return LZString.decompressFromBase64(b64);
}

function encodeLevelValue(json) {
  const b64 = LZString.compressToBase64(json);
  const head = Buffer.from([0x01]);
  return Buffer.concat([head, Buffer.from(b64, 'latin1')]);
}

function decodeSave(value) {
  const js = decodeLevelValue(value);
  return JSON.parse(js);
}

function encodeSave(obj) {
  return encodeLevelValue(JSON.stringify(obj));
}

// Access helpers for the JsonEx wrapped arrays.
function realArray(wrapped) {
  if (wrapped && Array.isArray(wrapped['@a'])) {
    return wrapped['@a'];
  }
  throw new Error('expected JsonEx wrapped array with "@a"');
}

function variables(save) {
  return realArray(save.variables._data);
}

function switches(save) {
  return realArray(save.switches._data);
}

module.exports = { decodeLevelValue, encodeLevelValue, decodeSave, encodeSave, realArray, variables, switches };
