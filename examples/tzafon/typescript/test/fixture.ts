import assert from 'node:assert/strict';

export const CODE = 'orbit-fixture';
export function response(action: Record<string, unknown> | null, safety = false, index = 0) {
  const item = action ? { id: `call_fixture_${index}`, type: 'computer_call', call_id: `call_fixture_${index}`, status: 'completed', pending_safety_checks: safety ? [{ id: 'review_fixture', code: 'fixture', message: 'Review needed' }] : [], action }
    : { id: 'msg_fixture', type: 'message', role: 'assistant', status: 'completed', content: [{ type: 'output_text', text: 'Complete', annotations: [] }] };
  return { id: `resp_fixture_${index}`, object: 'response', status: 'completed', model: 'tzafon.northstar-cua-fast-1.6', output: [item] };
}
export function wire(mode = 'protocol', realScreenshot = false) {
  const requests: Record<string, any>[] = [];
  const mock: typeof fetch = async (input, options) => {
    const request = new Request(input, options);
    assert.equal(new URL(request.url).pathname, '/v1/responses');
    assert.equal(request.method, 'POST');
    assert.equal(request.headers.get('Authorization'), 'Bearer fixture-provider-key');
    const body = await request.json();
    assert.equal(body.store, false);
    assert.ok(!('previous_response_id' in body));
    assert.equal(body.model, 'tzafon.northstar-cua-fast-1.6');
    assert.deepEqual(body.tools, [{ type: 'computer_use', environment: 'browser', display_width: 1024, display_height: 768 }]);
    if (realScreenshot) {
      const item = body.input.at(-1);
      const image = item.type === 'computer_call_output' ? item.output.image_url : item.content[1].image_url;
      const png = Buffer.from(image.split(',')[1], 'base64');
      assert.equal(png.subarray(0, 8).toString('base64'), 'iVBORw0KGgo=');
      assert.ok(png.length > 1000);
      assert.equal(png.readUInt32BE(16), 1024);
      assert.equal(png.readUInt32BE(20), 768);
    }
    requests.push(body);
    if (mode === 'reject') return Response.json({ error: { message: 'PRIVATE_FIXTURE_BODY' } }, { status: 401 });
    let action: Record<string, unknown> | null;
    if (mode === 'limit') action = { type: 'screenshot' };
    else if (mode === 'safety' || mode === 'out-of-bounds') action = { type: 'click', x: mode === 'out-of-bounds' ? 1000 : 160, y: 260, button: 'left' };
    else if (requests.length === 1) action = { type: 'point_and_type', x: 160, y: 260, text: CODE };
    else if (requests.length === 2) action = { type: 'keypress', keys: ['ENTER'] };
    else action = null;
    return Response.json(response(action, mode === 'safety', requests.length));
  };
  return { mock, requests };
}
