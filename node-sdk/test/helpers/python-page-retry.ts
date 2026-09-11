/** Retry only the known browser-loss failure in the read-only timeout example. */
export async function withPythonPageRetry<T>(example: string, run: () => Promise<T>): Promise<T> {
  try {
    return await run();
  } catch (error) {
    if (example !== 'sessions/configuration/timeout.ts') throw error;
    const stderr = error && typeof error === 'object' && 'stderr' in error
      ? String(error.stderr).replace(/\u001b\[[0-9;]*m/g, '') : '';
    // Inspect the final traceback: a cleanup failure can chain the original
    // TargetClosedError, but must not be mistaken for a safely retryable run.
    const traceback = stderr.slice(stderr.lastIndexOf('Traceback (most recent call last):'));
    if (!/^playwright\._impl\._errors\.TargetClosedError: Page\.goto: Target page, context or browser has been closed\s*$/m.test(traceback)) {
      throw error;
    }
    console.warn(`${example} (python): browser closed during navigation; retrying once with a fresh session after 5000ms`);
    await new Promise(resolve => setTimeout(resolve, 5000));
    return run();
  }
}
