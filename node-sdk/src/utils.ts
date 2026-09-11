/**
 * Helper function to format error messages
 */
import { spawn } from 'node:child_process';

function formatError(error: unknown): string {
	if (typeof error === 'object' && error !== null) {
		// If the error object has a message property, use it
		if ('message' in error && typeof error.message === 'string') {
			return error.message;
		}
		// Otherwise, try to stringify the object
		try {
			return JSON.stringify(error, null, 2);
		} catch {
			return String(error);
		}
	}
	if (error instanceof Error) {
		return error.message;
	}
	return String(error);
}

function openBrowser(url: string): void {
	const platform = process.platform;
	let command: string;
	let args: string[];

	if (platform === 'darwin') {
		command = 'open';
		args = [url];
	} else if (platform === 'win32') {
		command = 'rundll32';
		args = ['url.dll,FileProtocolHandler', url];
	} else {
		command = 'xdg-open';
		args = [url];
	}

	const child = spawn(command, args, {
		detached: true,
		stdio: 'ignore',
	});
	child.on('error', () => {
		// The viewer is a convenience path; avoid crashing the process if no
		// local browser opener exists in the current environment.
	});
	child.unref();
}

export { formatError, openBrowser };
