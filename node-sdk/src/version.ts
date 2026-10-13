declare const __SDK_VERSION__: string;
declare const __SDK_PACKAGE_NAME__: string;

// Injected at build time by tsup from package.json "version".
// Falls back to 'dev' when running outside a build (tsx, ts-node, tests).
export const SDK_VERSION: string = typeof __SDK_VERSION__ !== 'undefined' ? __SDK_VERSION__ : 'dev';
export const SDK_PACKAGE_NAME: string =
  typeof __SDK_PACKAGE_NAME__ !== 'undefined' ? __SDK_PACKAGE_NAME__ : 'notte-sdk';
