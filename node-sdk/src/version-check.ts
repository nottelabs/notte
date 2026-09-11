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

let hasStartedVersionCheck = false;

export function startVersionCheck(): void {
  if (hasStartedVersionCheck || !shouldCheckVersion()) {
    return;
  }

  hasStartedVersionCheck = true;

  const timer = setTimeout(() => {
    void checkForLatestVersion().catch(() => undefined);
  }, 0);

  timer.unref?.();
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

  if (!latestVersion || !isVersionGreater(latestVersion, currentVersion)) {
    return;
  }

  warnFn(
    `[${packageName}] A newer version is available: ${currentVersion} -> ${latestVersion}. ` +
      `Update with: npm install ${packageName}@latest`
  );
}

function shouldCheckVersion(
  currentVersion: string = SDK_VERSION,
  fetchFn: typeof fetch | undefined = globalThis.fetch,
  env: Env | undefined = getEnv()
): boolean {
  if (!fetchFn || !env || env[DISABLE_ENV] || env.NODE_ENV === 'test' || env.VITEST || env.CI) {
    return false;
  }

  return isPublishedVersion(currentVersion);
}

async function fetchLatestVersion(packageName: string, fetchFn: typeof fetch): Promise<string | undefined> {
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : undefined;
  const timeout = controller
    ? setTimeout(() => controller.abort(), VERSION_CHECK_TIMEOUT_MS)
    : undefined;

  timeout?.unref?.();

  try {
    const response = await fetchFn(`https://registry.npmjs.org/${encodeURIComponent(packageName)}/latest`, {
      headers: {
        accept: 'application/json',
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
