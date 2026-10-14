// Levelled diagnostics for the SDK. Messages below the configured level are
// dropped before they are built. Uses only `console`, so it is safe in edge
// and browser runtimes.

/** Minimum severity of SDK diagnostic logs; `silent` turns them off. */
export type LogLevel = 'debug' | 'info' | 'warn' | 'error' | 'silent';

/** Environment variable read when `NotteClient` is created without `logLevel`. */
export const LOG_LEVEL_ENV = 'NOTTE_LOG_LEVEL';
/** Only warnings and errors print unless a lower level is requested. */
export const DEFAULT_LOG_LEVEL: LogLevel = 'warn';

const SEVERITY: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40, silent: 50 };

export function isLogLevel(value: unknown): value is LogLevel {
  return typeof value === 'string' && Object.prototype.hasOwnProperty.call(SEVERITY, value);
}

function readEnvLogLevel(): string | undefined {
  try {
    return typeof process === 'undefined' ? undefined : process.env?.[LOG_LEVEL_ENV];
  } catch {
    return undefined;
  }
}

/** The explicit level, else `NOTTE_LOG_LEVEL` (`warning` is accepted for `warn`), else `warn`. */
export function resolveLogLevel(level?: LogLevel): LogLevel {
  if (level !== undefined) return level;
  const fromEnv = readEnvLogLevel()?.trim().toLowerCase();
  if (fromEnv === 'warning') return 'warn';
  return isLogLevel(fromEnv) ? fromEnv : DEFAULT_LOG_LEVEL;
}

export type LogMethod = Exclude<LogLevel, 'silent'>;

export class Logger {
  constructor(readonly level: LogLevel) {}

  isEnabled(level: LogMethod): boolean {
    return SEVERITY[level] >= SEVERITY[this.level];
  }

  log(level: LogMethod, message: string): void {
    if (this.isEnabled(level)) console[level](message);
  }
}
