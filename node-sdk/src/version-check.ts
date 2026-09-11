import { SDK_PACKAGE_NAME, SDK_VERSION } from '@/version';

const DISABLE_ENV = 'NOTTE_SDK_DISABLE_VERSION_CHECK';
const VERSION_CHECK_TIMEOUT_MS = 1_500;

type Env = Record<string, string | undefined>;

type VersionCheckOptions = {
  currentVersion?: string;
  packageName?: string;
  fetchFn?: typeof fetch;
  warnFn?: (message: string) => void;
  env?: Env;
};

type NpmLatestResponse = {
  version?: unknown;
};

// Mirrors the module globals of `notte_sdk.endpoints.base`: the registry is
// contacted at most once per process and the answer is cached so later 422
// validation errors can suggest the upgrade.
let versionCheckPerformed = false;
let cachedLatestVersion: string | undefined;

/**
 * Check the npm registry once per process and warn when a newer release exists.
 * Called by `NotteClient` on construction, like `check_and_warn_version_mismatch`
 * in the Python client. Never throws and never blocks the caller.
 */
export function startVersionCheck(): void {
  if (versionCheckPerformed || !shouldCheckVersion()) {
    return;
  }
  versionCheckPerformed = true;

  const timer = setTimeout(() => {
    void checkForLatestVersion().catch(() => undefined);
  }, 0);
  timer.unref?.();
}

/** Latest version seen on the registry during this process, if the check ran. */
export function getLatestKnownVersion(): string | undefined {
  return cachedLatestVersion;
}

/** True when `current` is strictly older than `latest`. Unparseable versions never suggest an upgrade. */
export function isVersionOlder(current: string, latest: string): boolean {
  return isVersionGreater(latest, current);
}

/**
 * When the registry reported a newer version, return it so error messages can
 * suggest the upgrade. Development builds never suggest one.
 */
export function upgradeSuggestion(currentVersion: string = SDK_VERSION): string | undefined {
  if (!cachedLatestVersion || !isPublishedVersion(currentVersion)) {
    return undefined;
  }
  return isVersionOlder(currentVersion, cachedLatestVersion) ? cachedLatestVersion : undefined;
}

export function createUpgradeErrorMessage(
  errorContext: string,
  latestVersion: string,
  originalError?: string,
  currentVersion: string = SDK_VERSION,
  packageName: string = SDK_PACKAGE_NAME,
): string {
  let message =
    `${errorContext}. This might be due to API schema changes. ` +
    `Current SDK version: ${currentVersion}, Latest available: ${latestVersion}. ` +
    `Either you made a mistake in the request arguments, or you should upgrade to the latest ` +
    `${packageName} version by running: 'npm install ${packageName}@${latestVersion}'`;
  if (originalError) {
    message += `. Original error: ${originalError}`;
  }
  return message;
}

export async function checkForLatestVersion(options: VersionCheckOptions = {}): Promise<void> {
  const currentVersion = options.currentVersion ?? SDK_VERSION;
  const packageName = options.packageName ?? SDK_PACKAGE_NAME;
  const fetchFn = options.fetchFn ?? globalThis.fetch;
  const warnFn = options.warnFn ?? console.warn;
  const env = options.env ?? getEnv();

  if (!shouldCheckVersion(currentVersion, fetchFn, env)) {
    return;
  }

  const latestVersion = await fetchLatestVersion(packageName, fetchFn);
  if (!latestVersion) {
    return;
  }
  cachedLatestVersion = latestVersion;

  if (!isVersionGreater(latestVersion, currentVersion)) {
    return;
  }

  warnFn(
    `⚠️ You are using ${packageName} version ${currentVersion}, but version ${latestVersion} is available on npm. ` +
      `Run 'npm install ${packageName}@${latestVersion}' to avoid any interruptions.`,
  );
}

/** Test hook: forget the once-per-process state. */
export function resetVersionCheckForTests(): void {
  versionCheckPerformed = false;
  cachedLatestVersion = undefined;
}

function shouldCheckVersion(
  currentVersion: string = SDK_VERSION,
  fetchFn: typeof fetch | undefined = globalThis.fetch,
  env: Env | undefined = getEnv(),
): boolean {
  if (!fetchFn || !env || env[DISABLE_ENV] || env.NODE_ENV === 'test' || env.VITEST || env.CI) {
    return false;
  }

  return isPublishedVersion(currentVersion);
}

async function fetchLatestVersion(packageName: string, fetchFn: typeof fetch): Promise<string | undefined> {
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : undefined;
  const timeout = controller ? setTimeout(() => controller.abort(), VERSION_CHECK_TIMEOUT_MS) : undefined;

  timeout?.unref?.();

  try {
    const response = await fetchFn(`https://registry.npmjs.org/${encodeURIComponent(packageName)}/latest`, {
      headers: {
        accept: 'application/json',
        'user-agent': `${packageName}/${SDK_VERSION} (https://github.com/nottelabs/notte)`,
      },
      signal: controller?.signal,
    });

    if (!response.ok) {
      return undefined;
    }

    const payload = (await response.json()) as NpmLatestResponse;
    return typeof payload.version === 'string' ? payload.version : undefined;
  } catch {
    return undefined;
  } finally {
    if (timeout) {
      clearTimeout(timeout);
    }
  }
}

function isPublishedVersion(version: string): boolean {
  return /^\d+\.\d+\.\d+/.test(version) && !version.includes('dev');
}

function isVersionGreater(candidate: string, current: string): boolean {
  const candidateVersion = parseSemver(candidate);
  const currentVersion = parseSemver(current);

  if (!candidateVersion || !currentVersion) {
    return false;
  }

  for (let index = 0; index < 3; index += 1) {
    if (candidateVersion.parts[index] > currentVersion.parts[index]) {
      return true;
    }

    if (candidateVersion.parts[index] < currentVersion.parts[index]) {
      return false;
    }
  }

  return currentVersion.prerelease.length > 0 && candidateVersion.prerelease.length === 0;
}

function parseSemver(version: string): { parts: [number, number, number]; prerelease: string } | undefined {
  const match = version.match(/^(\d+)\.(\d+)\.(\d+)(?:-([^+]+))?/);

  if (!match) {
    return undefined;
  }

  return {
    parts: [Number(match[1]), Number(match[2]), Number(match[3])],
    prerelease: match[4] ?? '',
  };
}

function getEnv(): Env | undefined {
  return typeof process !== 'undefined' ? process.env : undefined;
}
