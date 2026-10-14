import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { NotteClient } from '@/client';
import { NotteAPIError } from '@/errors';
import { config } from 'dotenv';
import { cleanupVaults } from './helpers/cleanup-vaults';
import { AGENT_TEST_TIMEOUT_MS, skipHeavyLive } from './helpers/live-scope';
config();

describe('Vault Integration Tests', () => {
	let client: NotteClient;
	let createdVaultIds: string[] = [];

	beforeEach(async () => {
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
		await cleanupVaults(client, createdVaultIds);
		createdVaultIds = [];
	});

	describe('Vault Creation', () => {
		it('should create a new vault', async () => {
			const newVault = client.Vault({ name: 'My Secure Vault' });

			// Trigger initialization by using the vault
			await newVault.listCredentials();

			expect(newVault.vaultId).toBeDefined();
			expect(typeof newVault.vaultId).toBe('string');
			expect(newVault.vaultId.length).toBeGreaterThan(0);

			createdVaultIds.push(newVault.vaultId);
		});

		it('should create a vault without name', async () => {
			const newVault = client.Vault();

			// Trigger initialization by using the vault
			await newVault.listCredentials();

			expect(newVault.vaultId).toBeDefined();
			createdVaultIds.push(newVault.vaultId);
		});

		it('should list the created vault with client.vaults.list()', async () => {
			const newVault = client.Vault({ name: 'Listed Vault' });
			await newVault.listCredentials();
			createdVaultIds.push(newVault.vaultId);

			const vaults = await client.vaults.list();
			expect(vaults.some(vault => vault.vault_id === newVault.vaultId)).toBe(true);
		});
	});

	describe('Credentials Management', () => {
		it('should add credentials for a website', async () => {
			const newVault = client.Vault({ name: 'Test Vault' });

			await newVault.addCredentials('https://github.com/', {
				email: 'user@example.com',
				password: 'secure-password-123', // pragma: allowlist secret
				mfa_secret: 'PYNT7I67RFS2EPR5' // pragma: allowlist secret
			});

			createdVaultIds.push(newVault.vaultId);

			// Verify credentials were added; the SDK and the API both normalise URLs to the root domain.
			const credentials = await newVault.listCredentials();
			expect(credentials.length).toBeGreaterThan(0);
			expect(credentials.some(c => c.url === 'github.com')).toBe(true);
		});

		it('should add credentials with auto-generated password', async () => {
			const newVault = client.Vault({ name: 'Test Vault' });

			const generatedPassword = newVault.generatePassword(16, true);
			await newVault.addCredentials('https://gmail.com/', {
				email: 'user@gmail.com',
				password: generatedPassword
			});

			createdVaultIds.push(newVault.vaultId);

			// Verify credentials were added
			const credentials = await newVault.listCredentials();
			expect(credentials.length).toBeGreaterThan(0);
		});

		it('should list all stored credentials', async () => {
			const newVault = client.Vault({ name: 'Test Vault' });

			await newVault.addCredentials('https://github.com/', {
				email: 'user@example.com',
				password: 'secure-password-123' // pragma: allowlist secret
			});

			createdVaultIds.push(newVault.vaultId);

			const credentials = await newVault.listCredentials();
			expect(Array.isArray(credentials)).toBe(true);
			expect(credentials.length).toBeGreaterThan(0);
			expect(credentials[0].url).toBeDefined();
		});

		it('should get specific credentials', async () => {
			const newVault = client.Vault({ name: 'Test Vault' });

			await newVault.addCredentials('https://github.com/', {
				email: 'user@example.com',
				password: 'secure-password-123' // pragma: allowlist secret
			});

			createdVaultIds.push(newVault.vaultId);

			const githubCreds = await newVault.getCredentials('https://github.com/');
			expect(githubCreds.email).toBe('user@example.com');
			expect(githubCreds.password).toBe('secure-password-123');
		});

		it('should reject getCredentials for an unknown website with a NotteAPIError', async () => {
			const newVault = client.Vault({ name: 'Test Vault' });
			await newVault.listCredentials();
			createdVaultIds.push(newVault.vaultId);

			await expect(newVault.getCredentials('https://nonexistent.example.com/')).rejects.toBeInstanceOf(NotteAPIError);
		});

		it('should report hasCredential', async () => {
			const newVault = client.Vault({ name: 'Test Vault' });

			await newVault.addCredentials('https://github.com/', {
				email: 'user@example.com',
				password: 'secure-password-123' // pragma: allowlist secret
			});
			createdVaultIds.push(newVault.vaultId);

			await expect(newVault.hasCredential('https://github.com/login')).resolves.toBe(true);
			await expect(newVault.hasCredential('github.com')).resolves.toBe(true);
			await expect(newVault.hasCredential('https://gitlab.com/')).resolves.toBe(false);
		});

		it('should delete specific credentials', async () => {
			const newVault = client.Vault({ name: 'Test Vault' });

			await newVault.addCredentials('https://gmail.com/', {
				email: 'user@gmail.com',
				password: 'password123' // pragma: allowlist secret
			});

			createdVaultIds.push(newVault.vaultId);

			// Verify credentials exist
			let credentials = await newVault.listCredentials();
			const initialCount = credentials.length;

			// Delete credentials
			await newVault.deleteCredentials('https://gmail.com/');

			// Verify credentials were deleted
			credentials = await newVault.listCredentials();
			expect(credentials.length).toBeLessThan(initialCount);
			await expect(newVault.hasCredential('https://gmail.com/')).resolves.toBe(false);
		});
	});

	describe('Password Generation', () => {
		it('should generate strong password with default settings', async () => {
			const newVault = client.Vault({ name: 'Test Vault' });
			await newVault.listCredentials(); // Initialize vault

			const password = newVault.generatePassword();
			expect(password).toBeDefined();
			expect(typeof password).toBe('string');
			expect(password.length).toBeGreaterThan(0);

			createdVaultIds.push(newVault.vaultId);
		});

		it('should generate password with custom length', async () => {
			const newVault = client.Vault({ name: 'Test Vault' });
			await newVault.listCredentials(); // Initialize vault

			const password = newVault.generatePassword(12);
			expect(password).toBeDefined();
			expect(typeof password).toBe('string');
			expect(password.length).toBe(12);

			createdVaultIds.push(newVault.vaultId);
		});

		it('should generate password without special chars', async () => {
			const newVault = client.Vault({ name: 'Test Vault' });
			await newVault.listCredentials(); // Initialize vault

			const password = newVault.generatePassword(15, false);
			expect(password).toBeDefined();
			expect(typeof password).toBe('string');
			expect(password.length).toBe(15);

			createdVaultIds.push(newVault.vaultId);
		});
	});

	describe.skipIf(skipHeavyLive)('Vault with Agent', () => {
		it('should use vault with Session and Agent', { timeout: AGENT_TEST_TIMEOUT_MS }, async () => {
			const newVault = client.Vault({ name: 'Test Vault' });

			await newVault.addCredentials('https://github.com/', {
				email: 'user@example.com',
				password: 'secure-password-123' // pragma: allowlist secret
			});

			createdVaultIds.push(newVault.vaultId);

			await client.Session({ proxies: false, headless: true }).use(async (session) => {
				const agent = client.Agent({
					session,
					max_steps: 3,
					vault_id: newVault.vaultId
				});

				const result = await agent.run({
					task: "Go to GitHub login page and describe what you see",
					url: "https://github.com/login"
				});

				expect(result).toBeDefined();
				expect(result.agent_id).toBeDefined();
				expect(result.status).toBe('closed');
				expect(result.success).toBeDefined();
				expect(result.answer).toBeDefined();
			});
		});
	});

	describe('Vault Deletion', () => {
		it('should delete entire vault', async () => {
			const newVault = client.Vault({ name: 'Test Vault' });
			await newVault.listCredentials(); // Initialize vault
			const vaultId = newVault.vaultId;

			await newVault.stop();

			// The deleted vault can no longer be opened.
			const deletedVault = client.Vault({ vault_id: vaultId });
			await expect(deletedVault.listCredentials()).rejects.toBeInstanceOf(NotteAPIError);
		});
	});

});
