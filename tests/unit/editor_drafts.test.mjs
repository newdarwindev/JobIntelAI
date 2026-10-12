import test from 'node:test';
import assert from 'node:assert/strict';
import {EditorDrafts} from '../../src/jobintel/web/drafts.js';

test('each posting retains its own text, URL and format while saved sources change', () => {
  const drafts = new EditorDrafts();
  const a = {text: 'Saved A', url: 'https://example.com/a', format: 'text'};
  const b = {text: 'Saved B', url: '', format: 'text'};
  drafts.sync('source:a', a);
  drafts.change('source:a', {...a, text: '<main>Private draft A</main>', format: 'html'});
  drafts.sync('source:b', b);
  drafts.change('source:b', {...b, text: 'Private draft B'});
  drafts.sync('source:a', {...a, text: 'Acquired A'});
  assert.equal(drafts.read('source:a').value.text, '<main>Private draft A</main>');
  assert.equal(drafts.read('source:a').value.format, 'html');
  assert.equal(drafts.read('source:b').value.text, 'Private draft B');
  drafts.discard('source:a');
  assert.equal(drafts.read('source:a').value.text, 'Acquired A');
  assert.equal(drafts.dirty('source:a'), false);
  assert.equal(drafts.dirty('source:b'), true);
});

test('pristine editors follow newly acquired sources', () => {
  const drafts = new EditorDrafts();
  drafts.sync('source:a', {text: ''});
  drafts.sync('source:a', {text: 'New saved source'});
  assert.equal(drafts.read('source:a').value.text, 'New saved source');
  assert.equal(drafts.dirty('source:a'), false);
});

test('a late save cannot consume edits made after submission', () => {
  const drafts = new EditorDrafts();
  drafts.sync('registry', {content: '', format: 'csv'});
  drafts.change('registry', {content: 'Submitted batch', format: 'json'});
  const submitted = drafts.capture('registry');
  drafts.change('registry', {content: 'Newer batch', format: 'csv'});
  assert.equal(drafts.accept(submitted), false);
  assert.equal(drafts.read('registry').value.content, 'Newer batch');
  assert.equal(drafts.accept(drafts.capture('registry')), true);
  drafts.sync('registry', {content: '', format: 'csv'});
  assert.equal(drafts.read('registry').value.content, '');
});

test('late errors and saves cannot affect a discarded and reopened editor', () => {
  const drafts = new EditorDrafts();
  drafts.sync('candidate:revision', {text: 'Saved profile'});
  drafts.change('candidate:revision', {text: 'Submitted profile'});
  const submitted = drafts.capture('candidate:revision');
  drafts.discard('candidate:revision');
  assert.equal(drafts.setError(submitted.key, 'Old validation failure', submitted.version), false);
  assert.equal(drafts.accept(submitted), false);
  assert.equal(drafts.read(submitted.key).value.text, 'Saved profile');
  assert.equal(drafts.read(submitted.key).error, '');
});

test('candidate revision drafts and validation errors survive revisiting their scope', () => {
  const drafts = new EditorDrafts();
  drafts.sync('candidate:old', {text: 'Old saved revision'});
  drafts.change('candidate:old', {text: '{invalid private JSON'});
  const submitted = drafts.capture('candidate:old');
  drafts.setError(submitted.key, 'Invalid candidate JSON', submitted.version);
  drafts.sync('candidate:new', {text: 'New saved revision'});
  drafts.sync('candidate:old', {text: 'Old saved revision'});
  assert.equal(drafts.read('candidate:old').value.text, '{invalid private JSON');
  assert.equal(drafts.read('candidate:old').error, 'Invalid candidate JSON');
  drafts.discard('candidate:old');
  assert.equal(drafts.read('candidate:old').error, '');
  assert.equal(drafts.read('candidate:new').value.text, 'New saved revision');
});

test('captured and returned values cannot mutate an editor behind its version check', () => {
  const drafts = new EditorDrafts();
  const saved = {text: 'Saved'};
  drafts.sync('source:a', saved);
  saved.text = 'Changed externally';
  const submitted = drafts.capture('source:a');
  submitted.value.text = 'Changed capture';
  drafts.read('source:a').value.text = 'Changed read';
  assert.equal(drafts.read('source:a').value.text, 'Saved');
  assert.equal(drafts.dirty('source:a'), false);
});
