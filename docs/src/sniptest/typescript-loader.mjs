// Match Vitest's local-SDK alias when examples execute in an isolated process.
export function resolve(specifier, context, nextResolve) {
  if (specifier === 'notte-sdk') {
    return { url: new URL('../../../node-sdk/dist/index.mjs', import.meta.url).href, shortCircuit: true };
  }
  // Explicit CDP examples import the SDK's installed Playwright peer directly.
  // Resolve from that package, not from the temporary artifact directory.
  if (specifier === 'playwright-core') {
    return nextResolve(specifier, {
      ...context,
      parentURL: new URL('../../../node-sdk/package.json', import.meta.url).href,
    });
  }
  return nextResolve(specifier, context);
}
