import { SDK_VERSION } from '@/version';

// The User-Agent the SDK sends to the Notte API: the SDK, its version, the Node runtime and,
// inside GitHub Actions, the repository, run and job running it, so failing sessions can be
// traced back to the CI job that started them. Only sent to the Notte API, and only from Node:
// browsers do not let a page set it.

const UNSAFE = /[^A-Za-z0-9._/-]/g;
const MAX_VALUE_LENGTH = 100;

type Env = Record<string, string | undefined>;

function value(env: Env, name: string): string | undefined {
  const raw = env[name];
  return raw ? raw.replace(UNSAFE, '_').slice(0, MAX_VALUE_LENGTH) : undefined;
}

/** `github-actions (repo=...; run=...; job=...)` inside a GitHub Actions job, otherwise undefined. */
export function githubActionsContext(env: Env): string | undefined {
  if (env.GITHUB_ACTIONS !== 'true') return undefined;
  const run = value(env, 'GITHUB_RUN_ID');
  const attempt = value(env, 'GITHUB_RUN_ATTEMPT');
  const fields: Array<[string, string | undefined]> = [
    ['repo', value(env, 'GITHUB_REPOSITORY')],
    ['run', run && attempt ? `${run}/${attempt}` : run],
    ['job', value(env, 'GITHUB_JOB')],
  ];
  const parts = fields.filter(([, v]) => v).map(([k, v]) => `${k}=${v}`);
  return `github-actions (${parts.join('; ')})`;
}

/** The SDK's User-Agent under Node, read from the environment on each call; undefined elsewhere. */
export function clientUserAgent(): string | undefined {
  if (typeof process === 'undefined' || !process.versions?.node) return undefined;
  const agent = `notte-sdk-node/${SDK_VERSION} (node ${process.versions.node}; ${process.platform})`;
  const ci = githubActionsContext(process.env);
  return ci === undefined ? agent : `${agent} ${ci}`;
}
