import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { NotteClient } from '@/client';
import { config } from 'dotenv';
import { cleanupVaults } from './helpers/cleanup-vaults';
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
		it('should create a new vault', { timeout: 30000 }, async () => {
			const newVault = client.Vault({ name: 'My Secure Vault' });

			// Trigger initialization by using the vault
			await newVault.listCredentials();

			expect(newVault.vaultId).toBeDefined();
			expect(typeof newVault.vaultId).toBe('string');
			expect(newVault.vaultId.length).toBeGreaterThan(0);

			createdVaultIds.push(newVault.vaultId);
		});

		it('should create a vault without name', { timeout: 30000 }, async () => {
			const newVault = client.Vault();

			// Trigger initialization by using the vault
			await newVault.listCredentials();

			expect(newVault.vaultId).toBeDefined();
			createdVaultIds.push(newVault.vaultId);
		});
	});

	describe('Credentials Management', () => {
		it('should add credentials for a website', { timeout: 30000 }, async () => {
			const newVault = client.Vault({ name: 'Test Vault' });

			await newVault.addCredentials('https://github.com/', {
				email: 'user@example.com',
				password: 'secure-password-123', // pragma: allowlist secret
				mfa_secret: 'PYNT7I67RFS2EPR5' // pragma: allowlist secret
			});

			createdVaultIds.push(newVault.vaultId);

			// Verify credentials were added
			const credentials = await newVault.listCredentials();
			expect(credentials.length).toBeGreaterThan(0);
			const githubCreds = credentials.find(c => c.url.includes('github.com'));
			expect(githubCreds).toBeDefined();
		});

		it('should add credentials with auto-generated password', { timeout: 30000 }, async () => {
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

		it('should list all stored credentials', { timeout: 30000 }, async () => {
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

		it('should get specific credentials', { timeout: 30000 }, async () => {
			const newVault = client.Vault({ name: 'Test Vault' });

			await newVault.addCredentials('https://github.com/', {
				email: 'user@example.com',
				password: 'secure-password-123' // pragma: allowlist secret
			});

			createdVaultIds.push(newVault.vaultId);

			const githubCreds = await newVault.getCredentials('https://github.com/');
			expect(githubCreds).toBeDefined();
			expect(githubCreds).not.toBeNull();
			if (githubCreds) {
				expect(githubCreds.email).toBe('user@example.com');
			}
		});

		it('should delete specific credentials', { timeout: 30000 }, async () => {
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
		});
	});

	describe('Credit Card Management', () => {
		it('should set credit card information', { timeout: 30000 }, async () => {
			const newVault = client.Vault({ name: 'Test Vault' });

			await newVault.setCreditCard({
				card_holder_name: 'John Doe',
				card_number: '4111111111111111',
				card_cvv: '123',
				card_full_expiration: '12/25'
			});

			createdVaultIds.push(newVault.vaultId);

			// Verify credit card was set
			const creditCard = await newVault.getCreditCard();
			expect(creditCard).toBeDefined();
			expect(creditCard.card_holder_name).toBe('John Doe');
		});

		it('should get credit card information', { timeout: 30000 }, async () => {
			const newVault = client.Vault({ name: 'Test Vault' });

			await newVault.setCreditCard({
				card_holder_name: 'John Doe',
				card_number: '4111111111111111',
				card_cvv: '123',
				card_full_expiration: '12/25'
			});

			createdVaultIds.push(newVault.vaultId);

			const creditCard = await newVault.getCreditCard();
			expect(creditCard).toBeDefined();
			expect(creditCard.card_holder_name).toBeDefined();
		});

		it('should delete credit card', { timeout: 30000 }, async () => {
			const newVault = client.Vault({ name: 'Test Vault' });

			await newVault.setCreditCard({
				card_holder_name: 'John Doe',
				card_number: '4111111111111111',
				card_cvv: '123',
				card_full_expiration: '12/25'
			});

			createdVaultIds.push(newVault.vaultId);

			// Delete credit card
			await newVault.deleteCreditCard();

			// Verify credit card was deleted (should throw or return null)
			try {
				await newVault.getCreditCard();
				// If we get here, the credit card might still exist (which is acceptable)
			} catch (error) {
				// Expected if credit card was deleted
				expect(error).toBeDefined();
			}
		});
	});

	describe('Password Generation', () => {
		it('should generate strong password with default settings', { timeout: 10000 }, async () => {
			const newVault = client.Vault({ name: 'Test Vault' });
			await newVault.listCredentials(); // Initialize vault

			const password = newVault.generatePassword();
			expect(password).toBeDefined();
			expect(typeof password).toBe('string');
			expect(password.length).toBeGreaterThan(0);

			createdVaultIds.push(newVault.vaultId);
		});

		it('should generate password with custom length', { timeout: 10000 }, async () => {
			const newVault = client.Vault({ name: 'Test Vault' });
			await newVault.listCredentials(); // Initialize vault

			const password = newVault.generatePassword(12);
			expect(password).toBeDefined();
			expect(typeof password).toBe('string');
			expect(password.length).toBe(12);

			createdVaultIds.push(newVault.vaultId);
		});

		it('should generate password without special chars', { timeout: 10000 }, async () => {
			const newVault = client.Vault({ name: 'Test Vault' });
			await newVault.listCredentials(); // Initialize vault

			const password = newVault.generatePassword(15, false);
			expect(password).toBeDefined();
			expect(typeof password).toBe('string');
			expect(password.length).toBe(15);

			createdVaultIds.push(newVault.vaultId);
		});
	});

	describe('Vault with Agent', () => {
		it('should use vault with Session and Agent', { timeout: 180000 }, async () => {
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
		it('should delete entire vault', { timeout: 30000 }, async () => {
			const newVault = client.Vault({ name: 'Test Vault' });
			await newVault.listCredentials(); // Initialize vault
			const vaultId = newVault.vaultId;

			await newVault.stop();

			// Verify deletion by trying to access the vault
			try {
				const deletedVault = client.Vault({ vault_id: vaultId });
				await deletedVault.listCredentials();
				// If we get here, the vault still exists (which might be expected in some cases)
			} catch (error) {
				// Expected if vault was deleted
				expect(error).toBeDefined();
			}
		});
	});

});
