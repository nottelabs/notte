import { describe, expect, it } from 'vitest';
import { NotteClient } from '@/client';

describe('client.Agent', () => {
  it('throws with the act loop snippet', () => {
    const client = new NotteClient({ apiKey: 'test-key' }); // pragma: allowlist secret
    let message = '';
    try {
      void client.Agent;
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toContain('client.Agent was removed');
    expect(message).toContain('await client.sessions.act(');
    expect(message).toContain("result?.status !== 'done'");
    expect(message).toContain('https://docs.notte.cc/features/sessions/act');
  });
});
