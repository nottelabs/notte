import assert from 'node:assert/strict';
import { test } from 'node:test';
import { describe } from '../src/demo.ts';
import { transport } from './transport.ts';

process.env.WATSONX_API_KEY = 'fixture-api-key'; // pragma: allowlist secret
process.env.WATSONX_PROJECT_ID = 'fixture-project';
process.env.WATSONX_MODEL_ID = 'fixture-model';

test('IAM exchange and image chat contract', async () => {
  const { mock, calls } = transport();
  const image = Buffer.from('fixture-image');
  assert.equal(await describe(image, mock), 'Visible page description');
  assert.equal(calls.length, 2);
  assert.equal(calls[0].url, 'https://iam.cloud.ibm.com/identity/token');
  assert.deepEqual(Object.fromEntries(calls[0].options.body as URLSearchParams), { grant_type: 'urn:ibm:params:oauth:grant-type:apikey', apikey: 'fixture-api-key' }); // pragma: allowlist secret
  assert.equal(calls[1].url, 'https://us-south.ml.cloud.ibm.com/ml/v1/text/chat?version=2024-05-31');
  assert.equal((calls[1].options.headers as Record<string, string>).Authorization, 'Bearer fixture-bearer');
  const body = JSON.parse(String(calls[1].options.body));
  assert.equal(body.project_id, 'fixture-project');
  assert.equal(body.model_id, 'fixture-model');
  assert.equal(body.max_tokens, 200);
  assert.equal(body.messages[0].content[1].image_url.url, `data:image/png;base64,${image.toString('base64')}`);
  for (const { options } of calls) {
    assert.equal(options.method, 'POST');
    assert.equal(options.redirect, 'error');
    assert.ok(options.signal);
  }
});

test('failed or invalid IAM never sends image', async () => {
  for (const mode of ['iam-reject', 'invalid-token']) {
    const { mock, calls } = transport(mode);
    await assert.rejects(describe(Buffer.from('fixture'), mock));
    assert.equal(calls.length, 1);
  }
});

test('model rejection and empty result fail', async () => {
  for (const mode of ['chat-reject', 'empty']) {
    const { mock } = transport(mode);
    await assert.rejects(describe(Buffer.from('fixture'), mock));
  }
});
