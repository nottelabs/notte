// Match Vitest's local-SDK alias when examples execute in an isolated process.
export function resolve(specifier, context, nextResolve) {
  if (specifier === 'notte-sdk') {
    return { url: new URL('../../../node-sdk/dist/index.mjs', import.meta.url).href, shortCircuit: true };
  }
  return nextResolve(specifier, context);
}
