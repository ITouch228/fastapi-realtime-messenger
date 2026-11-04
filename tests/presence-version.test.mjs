import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const source = readFileSync(
  new URL('../backend/app/static/js/core/store.js', import.meta.url),
  'utf8',
);
const { default: store } = await import(
  'data:text/javascript;base64,' + Buffer.from(source).toString('base64')
);

test('online v3 wins against delayed offline v2', () => {
  store.peerStatuses = {};
  let notifications = 0;
  const unsubscribe = store.subscribe('peerStatuses', () => {
    notifications += 1;
  });
  store.setPeerStatus(42, { online: true, last_seen: null, version: 3 });
  store.setPeerStatus(42, {
    online: false,
    last_seen: '2026-11-04T00:00:00Z',
    version: 2,
  });
  assert.equal(store.getPeerStatus(42).online, true);
  assert.equal(store.getPeerStatus(42).version, 3);
  assert.equal(notifications, 1);
  unsubscribe();
});

test('newer offline wins and repeated version is ignored', () => {
  store.peerStatuses = {};
  store.setPeerStatus(42, { online: true, last_seen: null, version: 4 });
  store.setPeerStatus(42, {
    online: false,
    last_seen: '2026-11-04T01:00:00Z',
    version: 5,
  });
  store.setPeerStatus(42, { online: true, last_seen: null, version: 5 });
  assert.equal(store.getPeerStatus(42).online, false);
  assert.equal(store.getPeerStatus(42).version, 5);
});

test('legacy unversioned update does not overwrite versioned status', () => {
  store.peerStatuses = {};
  store.setPeerStatus(42, { online: true, last_seen: null, version: 6 });
  store.setPeerStatus(42, { online: false, last_seen: null });
  assert.equal(store.getPeerStatus(42).online, true);
});
