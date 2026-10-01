import test from 'node:test';
import assert from 'node:assert/strict';
import {readScope, restoreScope, disableScope, scopeDescription} from './scope-controls.mjs';

test('scope controls default, restore, and disable during requests', () => {
  const fields = {'company-filter': {value: 'all'}, 'year-filter': {value: 'all'}};
  globalThis.document = {getElementById: id => fields[id]};
  assert.deepEqual(readScope(), {company: 'all', year: 'all'});
  restoreScope({company: 'NAB', year: '2024'});
  assert.deepEqual(readScope(), {company: 'NAB', year: '2024'});
  disableScope(true);
  assert.equal(fields['company-filter'].disabled, true);
  assert.equal(fields['year-filter'].disabled, true);
  disableScope(false); restoreScope();
  assert.deepEqual(readScope(), {company: 'all', year: 'all'});
  assert.equal(fields['year-filter'].disabled, false);
  delete globalThis.document;
});

test('scope description preserves precedence notices and handles old answers', () => {
  assert.deepEqual(scopeDescription({}), []);
  assert.deepEqual(scopeDescription({ui_scope: {summary: 'NAB / FY2024', notes: ['Question takes precedence.']}}),
    ['Question scope: NAB / FY2024', 'Question takes precedence.']);
});
