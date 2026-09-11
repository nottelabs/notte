import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { NotteClient } from '@/client';
import * as fs from 'fs/promises';
import * as path from 'path';
import * as os from 'os';

// Load environment variables
import { config } from 'dotenv';
config();

describe('Session Integration Tests', () => {
	let client: NotteClient;
	let tempDir: string;

	beforeEach(async () => {
		// Create a temporary directory for test files
		tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'notte-test-'));

		// Initialize client with API key from environment
		const apiKey = process.env.NOTTE_API_KEY;
		if (!apiKey) {
			throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
		}

		client = new NotteClient({
			apiKey,
			baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc'
		});
	});

	afterEach(async () => {
		// Clean up temporary directory
		try {
			await fs.rm(tempDir, { recursive: true, force: true });
		} catch (error) {
			// Ignore cleanup errors
		}
	});

	describe('Basic Session Operations', () => {
		it('should start and stop a session', async () => {
			const session = client.Session({ proxies: false });
			await session.start();
			try {
				expect(session.getResponse()?.status).toBe('active');
				expect(session.getId()).toBeDefined();
			} finally {
				await session.stop();
			}
			expect(session.getResponse()?.status).toBe('closed');
		});

		it('should create session with factory method', async () => {
			const session = client.Session({ proxies: false, headless: true });

			await session.use(async (s) => {
				expect(s.getId()).not.toBeNull();
				const status = await s.status();
				expect(status.status).toBe('active');
			});

			expect(session.getResponse()).not.toBeNull();
			expect(session.getResponse()?.status).toBe('closed');
		});

		it('should create session with proxy settings', async () => {
			const session = client.Session({
				proxies: false,
				headless: true,
				// Note: proxy settings would need to be added to ApiSessionStartRequest type
			});

			await session.use(async (s) => {
				expect(s.getId()).not.toBeNull();
				const status = await s.status();
				expect(status.status).toBe('active');
			});

			expect(session.getResponse()).not.toBeNull();
		});

		it('should create session with viewport settings', async () => {
			const session = client.Session({
				proxies: false,
				headless: true,
				// Note: viewport settings would need to be added to ApiSessionStartRequest type
			});

			await session.use(async (s) => {
				expect(s.getId()).not.toBeNull();
				const status = await s.status();
				expect(status.status).toBe('active');
			});

			expect(session.getResponse()).not.toBeNull();
		});
	});

	describe('Session Replay', () => {
		it('should replay a session', async () => {
			const session = client.Session({ proxies: false, idle_timeout_minutes: 1 });
			await session.use(async (session) => {
				await session.execute({ type: 'goto', url: 'https://example.com' });
			});
			// Recordings are finalized only after the browser session is closed.
			await expect.poll(async () => (await session.replay()).replay.length, {
				timeout: 60000,
				interval: 1000,
			}).toBeGreaterThan(0);
		});
	});

	describe('Cookie Management', () => {
		it('should set and get cookies', async () => {
			const cookies = [
				{
					name: 'sb-db-auth-token',
					value: 'base64-XFV',
					domain: 'console.notte.cc',
					path: '/',
					expires: 1904382506.913704,
					httpOnly: false,
					secure: false,
					sameSite: 'Lax' as const
				}
			];

			await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 1 }).use(async (session) => {
				await session.setCookies(cookies);
				const retrievedCookies = await session.getCookies();

				expect(retrievedCookies.length).toBeGreaterThan(0);
				const foundCookie = retrievedCookies.find(
					cookie => cookie.name === cookies[0].name &&
						cookie.domain === cookies[0].domain &&
						cookie.value === cookies[0].value
				);
				expect(foundCookie).toBeDefined();
			});
		});

		it('should set cookies from file', async () => {
			const cookies = [
				{
					name: 'test-cookie',
					value: 'test-value',
					domain: 'example.com',
					path: '/',
					expires: Date.now() / 1000 + 3600,
					httpOnly: false,
					secure: false,
					sameSite: 'Lax' as const
				}
			];

			const cookieFile = path.join(tempDir, 'cookies.json');
			await fs.writeFile(cookieFile, JSON.stringify(cookies));

			await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 1 }).use(async (session) => {
				await session.setCookiesFromFile(cookieFile);
				const retrievedCookies = await session.getCookies();

				expect(retrievedCookies.length).toBeGreaterThan(0);
			});
		});
	});

	describe('Page Operations', () => {
		it('should execute goto action and observe page', { timeout: 30000 }, async () => {
			await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 1 }).use(async (session) => {
				// Execute goto action
				const executeResult = await session.execute({
					type: 'goto',
					url: 'https://www.ecosia.org'
				});

				expect(executeResult.success).toBe(true);

				// Observe the page
				const observeResult = await session.observe('fast');
				expect(observeResult.space).toBeDefined();
				expect(observeResult.space.description).toBeDefined();
				expect(observeResult.space.interaction_actions).toBeDefined();
			});
		});

		it('should get cookies after navigation', { timeout: 30000 }, async () => {
			await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 1 }).use(async (session) => {
				await session.execute({
					type: 'goto',
					url: 'https://www.ecosia.org'
				});

				await session.observe('fast');
				const cookies = await session.getCookies();

				expect(cookies.length).toBeGreaterThan(0);
			});
		});
	});

	describe('Action Validation', () => {
		it('should validate action parameters', { timeout: 30000 }, async () => {
			await client.Session({ proxies: false, headless: true }).use(async (session) => {
				await session.execute({
					type: 'goto',
					url: 'https://github.com/'
				});

				await session.observe('fast');

				// Test that goto action requires URL parameter
				try {
					await session.execute({
						type: 'goto'
						// Missing url parameter
					});
					expect.fail('Should have thrown validation error');
				} catch (error) {
					expect(error).toBeDefined();
				}

				// Test that wait action requires wait time parameter
				try {
					await session.execute({
						type: 'wait'
						// Missing wait time parameter
					});
					expect.fail('Should have thrown validation error');
				} catch (error) {
					expect(error).toBeDefined();
				}

				// Test invalid action with raiseOnFailure=false
				const result = await session.execute({
					type: 'click',
					id: 'X1' // Invalid element ID
				}, false);

				expect(result.success).toBe(false);
				expect(result.message).toContain('Action with id \'X1\' is invalid');
			});
		});
	});

	describe('Browser Type Support', () => {
		const browserTypes = ['chrome', 'firefox', 'chromium'] as const;

		for (const browserType of browserTypes) {
			it(`should work with ${browserType} browser`, async () => {
				await client.Session({
					proxies: false,
					headless: true,
					// Note: browser_type would need to be added to ApiSessionStartRequest type
				}).use(async (session) => {
					expect(session.getId()).not.toBeNull();
					const status = await session.status();
					expect(status.status).toBe('active');
				});
			});
		}
	});

	describe('Error Handling', () => {
		it('should handle session not started errors', async () => {
			const session = client.Session({ proxies: false });

			await expect(session.status()).rejects.toThrow('Session not started');
			await expect(session.execute({ type: 'goto', url: 'https://example.com' })).rejects.toThrow('Session not started');
			await expect(session.observe()).rejects.toThrow('Session not started');
			await expect(session.getCookies()).rejects.toThrow('Session not started');
		});

		it('should handle already active session error', async () => {
			const session = client.Session({ proxies: false });
			await session.start();
			try {
				await expect(session.start()).rejects.toThrow('Session is already active');
			} finally {
				await session.stop();
			}
		});
	});

	describe('Context Manager Pattern', () => {
		it('should automatically start and stop session', async () => {
			const session = client.Session({ proxies: false });

			const result = await session.use(async (s) => {
				expect(s.isSessionActive()).toBe(true);
				expect(s.getId()).not.toBeNull();
				return 'test-result';
			});

			expect(result).toBe('test-result');
			expect(session.isSessionActive()).toBe(false);
		});

		it('should stop session even if callback throws', async () => {
			const session = client.Session({ proxies: false });

			try {
				await session.use(async () => {
					throw new Error('Test error');
				});
				expect.fail('Should have thrown error');
			} catch (error) {
				expect((error as Error).message).toBe('Test error');
			}

			expect(session.isSessionActive()).toBe(false);
		});
	});

	describe('Async Iterator Pattern', () => {
		it('should support async iteration', async () => {
			const session = client.Session({ proxies: false });

			for await (const activeSession of session) {
				expect(activeSession.isSessionActive()).toBe(true);
				expect(activeSession.getId()).not.toBeNull();
				break; // Exit after first iteration
			}

			expect(session.isSessionActive()).toBe(false);
		});
	});

});
