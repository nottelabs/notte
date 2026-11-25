// @sniptest filename=onepassword_autofill.ts
// @sniptest typecheck_only=true
// Run this yourself, in your own terminal, on the machine where 1Password runs.
// Never run it through an agent: the approval link must stay out of a model's context.
import { execFile } from 'node:child_process';

type AccessRequest = { id: string; state: string; app_link: string | null; grants: { id: string; website: string | null }[] };
type Fill = { status: string; url: string };

async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`https://api.notte.cc${path}`, {
    method,
    headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}`, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${method} ${path}: ${response.status} ${await response.text()}`);
  return (response.status === 204 ? undefined : await response.json()) as T;
}

function openInBrowser(link: string): void {
  const opener = process.platform === 'darwin' ? 'open' : process.platform === 'win32' ? 'explorer.exe' : 'xdg-open';
  execFile(opener, [link], (error) => {
    if (error) console.error('Could not open a browser for the approval link');
  });
}

function isLoginStep(url: string): boolean {
  // GitHub's sign-in form and the page it shows after a refused login. Adapt to your site.
  return ['/login', '/session'].includes(new URL(url).pathname);
}

// 1. Start a session with 1Password. It stays `authenticating` until you release it.
const { session_id: sessionId } = await api<{ session_id: string }>('POST', '/sessions/start', { onepassword: true });
try {
  // 2. Ask for access to one login
  let request = await api<AccessRequest>('POST', `/sessions/${sessionId}/onepassword/access-requests`, {
    goal: 'Sign in to GitHub to review open pull requests',
    entries: [{ website: 'https://github.com', reason: 'Review pull requests' }],
  });
  // Open the approval link in your browser, without printing it.
  // From an agent, send it to the person through a channel the model cannot read instead.
  if (request.app_link) openInBrowser(request.app_link);

  // 3. Wait for the decision
  while (request.state === 'pending') {
    await new Promise((resolve) => setTimeout(resolve, 5_000));
    request = await api<AccessRequest>('GET', `/sessions/${sessionId}/onepassword/access-requests/${request.id}`);
  }
  if (request.state !== 'resolved' || request.grants.length === 0) {
    throw new Error(`Access was not granted: ${request.state}`);
  }
  const grantId = request.grants[0].id;

  // 4. 1Password fills and submits the login form, one page per call
  let body: { grant_id: string; url?: string } = { grant_id: grantId, url: 'https://github.com/login' };
  let pageUrl = '';
  for (let attempt = 0; attempt < 3; attempt++) {
    const fill = await api<Fill>('POST', `/sessions/${sessionId}/onepassword/fill`, body);
    // `fill_submitted` means the form was sent, not that the site accepted it
    if (fill.status !== 'fill_submitted') throw new Error(`1Password did not submit the form: ${fill.status}`);
    pageUrl = fill.url;
    if (!isLoginStep(pageUrl)) break;
    // Still on a login page: fill the current page again
    body = { grant_id: grantId };
  }
  if (isLoginStep(pageUrl)) throw new Error(`Sign-in did not finish, still at ${pageUrl}`);

  // 5. Release the session to your code. Fills stop for good after this.
  await api<void>('POST', `/sessions/${sessionId}/onepassword/release`);
} catch (error) {
  try {
    await fetch(`https://api.notte.cc/sessions/${sessionId}/stop`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` },
    });
  } catch {
    // keep the original error
  }
  throw error;
}

// Released: connect to the session as you would to any other, and check that you are signed in
export const releasedSession = sessionId;
