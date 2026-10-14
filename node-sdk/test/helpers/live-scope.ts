// CI sets NOTTE_LIVE_SCOPE=smoke on pull requests to skip the slowest live tests
// (agents, personas, vault with an agent). Main, scheduled and manual runs set
// "full", and local runs leave it unset, so those run every test.
export const skipHeavyLive = process.env.NOTTE_LIVE_SCOPE === 'smoke';

// Agent runs take several model steps against a shared staging API.
export const AGENT_TEST_TIMEOUT_MS = 180_000;
