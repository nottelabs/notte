// @sniptest filename=onepassword_autofill.ts
// @sniptest typecheck_only=true
type AccessRequest = { id: string; state: string; app_link: string | null; grants: { id: string; website: string | null }[] };

async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`https://api.notte.cc${path}`, {
    method,
    headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}`, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${method} ${path}: ${response.status} ${await response.text()}`);
  return (response.status === 204 ? undefined : await response.json()) as T;
}

// 1. Start a session with 1Password. It stays `authenticating` until you release it.
const { session_id: sessionId } = await api<{ session_id: string }>('POST', '/sessions/start', { onepassword: true });
try {
  // 2. Ask for access to one login
  let request = await api<AccessRequest>('POST', `/sessions/${sessionId}/onepassword/access-requests`, {
    goal: 'Sign in to GitHub to review open pull requests',
    entries: [{ website: 'https://github.com', reason: 'Review pull requests' }],
  });
  // Send the link to the person who approves in 1Password. Never give it to a model.
  console.log('Approve in 1Password:', request.app_link);

  // 3. Wait for the decision
  while (request.state === 'pending') {
    await new Promise((resolve) => setTimeout(resolve, 5_000));
    request = await api<AccessRequest>('GET', `/sessions/${sessionId}/onepassword/access-requests/${request.id}`);
  }
  if (request.state !== 'resolved' || request.grants.length === 0) {
    throw new Error(`Access was not granted: ${request.state}`);
  }
  const grantId = request.grants[0].id;

  // 4. 1Password fills and submits the login form
  const fill = await api<{ status: string; url: string }>('POST', `/sessions/${sessionId}/onepassword/fill`, {
    grant_id: grantId,
    url: 'https://github.com/login',
  });
  // `fill_submitted` means the form was sent. The page URL shows whether the site accepted it.
  console.log(fill.status, fill.url);

  // 5. Release the session to your code
  await api<void>('POST', `/sessions/${sessionId}/onepassword/release`);
} catch (error) {
  await fetch(`https://api.notte.cc/sessions/${sessionId}/stop`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` },
  });
  throw error;
}

// Signed in: connect to the session as you would to any other
export const signedInSession = sessionId;
