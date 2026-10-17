import assert from 'node:assert/strict';

export function transport(mode = 'fixture', screenshot = false) {
  const calls: { url: string; options: RequestInit }[] = [];
  const mock: typeof fetch = async (input, options) => {
    calls.push({ url: String(input), options: options! });
    if (calls.length === 1) {
      if (mode === 'iam-reject') return Response.json({ error: 'PRIVATE_FIXTURE_BODY' }, { status: 401 });
      return Response.json(mode === 'invalid-token' ? {} : { access_token: 'fixture-bearer' });
    }
    const body = JSON.parse(String(options?.body));
    if (screenshot) {
      const png = Buffer.from(body.messages[0].content[1].image_url.url.split(',')[1], 'base64');
      assert.equal(png.subarray(0, 8).toString('base64'), 'iVBORw0KGgo=');
      assert.ok(png.length > 1000);
    }
    if (mode === 'chat-reject') return Response.json({ error: 'PRIVATE_FIXTURE_BODY' }, { status: 403 });
    return Response.json({ choices: [{ message: { content: mode === 'empty' ? ' ' : 'Visible page description' } }] });
  };
  return { mock, calls };
}
