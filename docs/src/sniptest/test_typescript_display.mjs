import { test } from 'node:test';
import assert from 'node:assert/strict';
import { hiddenAssignmentDeclarations } from './typescript_display.mjs';

test('detects declarations cropped out of an otherwise valid tester', () => {
  assert.deepEqual(hiddenAssignmentDeclarations(`// @sniptest show=2-3
let title: string;
title = 'Example';
console.log(title);
`), ['title']);
});

test('allows visible declarations and contextual inputs', () => {
  assert.deepEqual(hiddenAssignmentDeclarations(`// @sniptest show=1-3
let title: string;
title = 'Example';
console.log(client, title);
`), []);
});

test('resolves shadowed variables in their own scope', () => {
  assert.deepEqual(hiddenAssignmentDeclarations(`// @sniptest show=2-5
let title: string;
{
  let title: string;
  title = 'Example';
}
`), []);
});
