// @sniptest filename=eval_js.ts
// @sniptest show=1-12
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session();
await session.use(async () => {
  await session.execute({ type: 'goto', url: 'https://notte.cc/' });
  // evaluateJs returns the evaluated string; failures raise with the JS error
  const title = await session.evaluateJs('document.title');
  // objects and arrays come back as JSON
  const links = JSON.parse(await session.evaluateJs("Array.from(document.querySelectorAll('a')).map(a => a.href)"));
});

const status = await session.status();
// Validate persisted evaluation output without exposing checks in the lesson.
const evaluations = status.steps?.flatMap(step => {
  const value = step.value as {
    action?: { type?: string };
    success?: boolean;
    data?: { markdown?: string };
  } | undefined;
  return value?.action?.type === 'evaluate_js' && value.success && typeof value.data?.markdown === 'string'
    ? [value.data.markdown] : [];
}) ?? [];
if (evaluations.length !== 2) throw new Error('Expected two successful JavaScript evaluations');
if (!evaluations[0].toLowerCase().includes('notte')) throw new Error('Missing Notte page title');
const links: unknown = JSON.parse(evaluations[1]);
if (!Array.isArray(links) || links.length === 0 || !links.every(link => typeof link === 'string')) {
  throw new Error('Expected a nonempty array of link URLs');
}
if (!links.some(link => link.startsWith('https://') && link.includes('notte'))) {
  throw new Error('Expected a Notte HTTPS link');
}

export { status };
