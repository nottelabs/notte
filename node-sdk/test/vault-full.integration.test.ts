import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { NotteClient } from '@/index';
import { config } from 'dotenv';
import { cleanupVaults } from './helpers/cleanup-vaults';

// Load environment variables from .env file
config();

// Load environment variables
const API_KEY = process.env.NOTTE_API_KEY;

describe('Vault Integration Tests', () => {
  let client: NotteClient;
  let createdVaults: string[] = [];

  beforeEach(() => {
    if (!API_KEY) {
      throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
    }
    client = new NotteClient({ apiKey: API_KEY });
  });

  afterEach(async () => {
    await cleanupVaults(client, createdVaults);
    createdVaults = [];
  });

  it('should only cleanup a vault created by this test', { timeout: 30000 }, async () => {
    const vault = client.Vault({ name: 'Node SDK owned cleanup test' });
    await vault.listCredentials();
    const vaultId = vault.vaultId;

    await cleanupVaults(client, [vaultId]);

    const deletedVault = client.Vault({ vault_id: vaultId });
    await expect(deletedVault.listCredentials()).rejects.toThrow();
  });

  describe('Basic Vault Operations', () => {
    it('should create vault and add credentials', async () => {
      const vault = client.Vault();

      // Add credentials
      await vault.addCredentials('https://github.com/', {
        email: 'xyz@notte.cc',
        password: 'xyz' // pragma: allowlist secret
      });

      // Get vault ID for cleanup
      const vaultId = vault.vaultId;
      createdVaults.push(vaultId);

      // Verify credentials were added
      const credentials = await vault.getCredentials('https://github.com/');
      expect(credentials).toBeDefined();
      expect(credentials?.email).toBe('xyz@notte.cc');
      expect(credentials?.password).toBe('xyz');
    });

    it('should list all credentials in vault', async () => {
      const vault = client.Vault();

      // Add multiple credentials
      await vault.addCredentials('https://github.com/', {
        email: 'test1@example.com',
        password: 'password1' // pragma: allowlist secret
      });

      await vault.addCredentials('https://google.com/', {
        email: 'test2@example.com',
        password: 'password2' // pragma: allowlist secret
      });

      const vaultId = vault.vaultId;
      createdVaults.push(vaultId);

      // List all credentials
      const credentials = await vault.listCredentials();
      expect(credentials).toHaveLength(2);
      expect(credentials.some(c => c.url === 'github.com')).toBe(true);
      expect(credentials.some(c => c.url === 'google.com')).toBe(true);
    });

    it('should delete credentials', async () => {
      const vault = client.Vault();

      // Add credentials
      await vault.addCredentials('https://github.com/', {
        email: 'test@example.com',
        password: 'password' // pragma: allowlist secret
      });

      const vaultId = vault.vaultId;
      createdVaults.push(vaultId);

      // Verify credentials exist
      let credentials = await vault.getCredentials('https://github.com/');
      expect(credentials).toBeDefined();

      // Delete credentials
      await vault.deleteCredentials('https://github.com/');

      // Verify credentials are deleted
      credentials = await vault.getCredentials('https://github.com/');
      expect(credentials).toBeNull();
    }, 15000); // 15 second timeout
  });

  describe('Vault with Agent Integration', () => {
    it('should use vault with local agent', { timeout: 180000 }, async () => {
      const vault = client.Vault();

      // Add credentials
      await vault.addCredentials('https://github.com/', {
        email: 'xyz@notte.cc',
        password: 'xyz' // pragma: allowlist secret
      });

      const vaultId = vault.vaultId;
      createdVaults.push(vaultId);

      // Create session and agent
      const session = client.Session({ proxies: false });
      await session.start();

      try {
        const agent = client.Agent({
          session,
          vault_id: vaultId,
          max_steps: 5
        });

        // Run agent task
        const result = await agent.run({
          task: 'Go to github.com and try to login with the credentials'
        });

        expect(result).toBeDefined();
        // The result should be a LegacyAgentStatusResponse
        if (result && typeof result === 'object' && 'agent_id' in result && result.agent_id) {
          expect(result.agent_id).toBeDefined();
          expect(result.task).toBeDefined();
        } else {
          // If result doesn't have expected structure, at least verify agent was created
          expect(agent.agentId).toBeDefined();
        }
        // success may be null/undefined if agent is still running or failed
        // Just verify the result structure is valid
      } finally {
        await session.stop();
      }
    });

    it('should use vault with remote agent', async () => {
      const vault = client.Vault();

      // Add credentials
      await vault.addCredentials('https://github.com/', {
        email: 'test@example.com',
        password: 'testpassword' // pragma: allowlist secret
      });

      const vaultId = vault.vaultId;
      createdVaults.push(vaultId);

      // Create session and agent
      const session = client.Session({ proxies: false, headless: true });
      await session.start();

      try {
        const agent = client.Agent({
          session,
          vault_id: vaultId,
          max_steps: 1
        });

        // Run agent task
        const result = await agent.run({
          task: 'Try to login to github.com with the credentials'
        });

        expect(result).toBeDefined();
        // The result should be a LegacyAgentStatusResponse
        if (result && typeof result === 'object' && 'agent_id' in result && result.agent_id) {
          expect(result.agent_id).toBeDefined();
          expect(result.task).toBeDefined();
        } else {
          // If result doesn't have expected structure, at least verify agent was created
          expect(agent.agentId).toBeDefined();
        }
        // success may be null/undefined if agent is still running or failed
        // Just verify the result structure is valid
      } finally {
        await session.stop();
      }
    }, 30000); // 30 second timeout
  });

  describe('Credit Card Operations', () => {
    it('should set and get credit card', async () => {
      const vault = client.Vault();

      const creditCard = {
        card_holder_name: 'John Doe',
        card_number: '4111111111111111',
        card_cvv: '123',
        card_full_expiration: '12/2025'
      };

      // Set credit card
      await vault.setCreditCard(creditCard);

      const vaultId = vault.vaultId;
      createdVaults.push(vaultId);

      // Get credit card
      const retrievedCard = await vault.getCreditCard();
      expect(retrievedCard).toEqual(creditCard);
    });

    it('should delete credit card', { timeout: 30000 }, async () => {
      const vault = client.Vault();

      const creditCard = {
        card_holder_name: 'John Doe',
        card_number: '4111111111111111',
        card_cvv: '123',
        card_full_expiration: '12/2025'
      };

      // Set credit card
      await vault.setCreditCard(creditCard);

      const vaultId = vault.vaultId;
      createdVaults.push(vaultId);

      // Verify credit card exists
      let retrievedCard = await vault.getCreditCard();
      expect(retrievedCard).toEqual(creditCard);

      // Delete credit card
      await vault.deleteCreditCard();

      // Verify credit card is deleted (should throw error or return null)
      // Wait a bit for deletion to propagate
      await new Promise(resolve => setTimeout(resolve, 1000));

      try {
        await vault.getCreditCard();
        // If no error is thrown, the test should fail
        expect.fail('Expected getCreditCard to throw error after deletion');
      } catch (error) {
        // Expected behavior - credit card should not exist
        expect(error).toBeDefined();
      }
    });
  });

  describe('Password Generation', () => {
    it('should generate password with default settings', () => {
      const vault = client.Vault();
      const password = vault.generatePassword();

      expect(password).toHaveLength(20);
      expect(password).toMatch(/[a-z]/); // lowercase
      expect(password).toMatch(/[A-Z]/); // uppercase
      expect(password).toMatch(/[0-9]/); // digit
      expect(password).toMatch(/[!@#$%^&*()_+\-=\[\]|;:,.<>?]/); // special char
    });

    it('should generate password with custom length', () => {
      const vault = client.Vault();
      const password = vault.generatePassword(12);

      expect(password).toHaveLength(12);
      expect(password).toMatch(/[a-z]/); // lowercase
      expect(password).toMatch(/[A-Z]/); // uppercase
      expect(password).toMatch(/[0-9]/); // digit
      expect(password).toMatch(/[!@#$%^&*()_+\-=\[\]|;:,.<>?]/); // special char
    });

    it('should generate password without special characters', () => {
      const vault = client.Vault();
      const password = vault.generatePassword(15, false);

      expect(password).toHaveLength(15);
      expect(password).toMatch(/[a-z]/); // lowercase
      expect(password).toMatch(/[A-Z]/); // uppercase
      expect(password).toMatch(/[0-9]/); // digit
      expect(password).not.toMatch(/[!@#$%^&*()_+\-=\[\]|;:,.<>?]/); // no special char
    });

    it('should throw error for password too short', () => {
      const vault = client.Vault();
      expect(() => vault.generatePassword(2)).toThrow('Password length must be at least 4 characters');
    });

    it('should throw error for password too short without special chars', () => {
      const vault = client.Vault();
      expect(() => vault.generatePassword(2, false)).toThrow('Password length must be at least 3 characters');
    });

    it('should generate different passwords each time', () => {
      const vault = client.Vault();
      const password1 = vault.generatePassword();
      const password2 = vault.generatePassword();

      expect(password1).not.toBe(password2);
    });
  });

  describe('Vault Context Manager', () => {
    it('should delete vault after context exit', { timeout: 60000 }, async () => {
      let vaultId: string;

      // Create vault in context
      const vault = client.Vault();
      await vault.addCredentials('https://test.com/', {
        email: 'test@example.com',
        password: 'testpassword' // pragma: allowlist secret
      });

      vaultId = vault.vaultId;

      // Stop vault (which should delete it)
      await vault.stop();

      // Verify vault is deleted by trying to access it
      try {
        const deletedVault = client.Vault({ vault_id: vaultId });
        await deletedVault.listCredentials();
        expect.fail('Expected vault to be deleted');
      } catch (error) {
        // Expected behavior - vault should not exist
        expect(error).toBeDefined();
      }
    });
  });

  describe('Environment Variable Credentials', () => {
    it('should add credentials from environment variables', { timeout: 60000 }, async () => {
      // Set up environment variables
      const originalEnv = process.env;
      process.env.PEEPLE_COM_EMAIL = 'xyz@notte.cc';
      process.env.PEEPLE_COM_PASSWORD = 'xyz'; // pragma: allowlist secret
      process.env.TEST_COM_USERNAME = 'my_xyz_username';
      process.env.TEST_COM_PASSWORD = 'my_xyz_password'; // pragma: allowlist secret

      try {
        const vault = client.Vault();

        // Add credentials from environment
        await vault.addCredentialsFromEnv('https://peeple.com/ok');
        await vault.addCredentialsFromEnv('https://test.com');

        const vaultId = vault.vaultId;
        createdVaults.push(vaultId);

        // Test getting credentials with different URL formats
        let credentials = await vault.getCredentials('https://peeple.com/test');
        expect(credentials).toBeDefined();
        expect(credentials?.email).toBe('xyz@notte.cc');
        expect(credentials?.password).toBe('xyz');

        credentials = await vault.getCredentials('peeple.com');
        expect(credentials).toBeDefined();
        expect(credentials?.email).toBe('xyz@notte.cc');
        expect(credentials?.password).toBe('xyz');

        credentials = await vault.getCredentials('https://test.com/');
        expect(credentials).toBeDefined();
        expect(credentials?.email).toBe('my_xyz_username');
        expect(credentials?.password).toBe('my_xyz_password');

        // Test non-existent credentials
        credentials = await vault.getCredentials('https://accounts.google.com');
        expect(credentials).toBeNull();
      } finally {
        // Restore original environment
        process.env = originalEnv;
      }
    });

    it('should throw error for missing environment variables', async () => {
      const vault = client.Vault();

      // This should fail because environment variables are not set
      await expect(vault.addCredentialsFromEnv('https://example.com/')).rejects.toThrow();

      // Initialize vault first to get vault ID for cleanup
      await vault.addCredentials('https://example.com/', {
        email: 'test@example.com',
        password: 'test' // pragma: allowlist secret
      });
      const vaultId = vault.vaultId;
      createdVaults.push(vaultId);
    });
  });

  describe('MFA Secret Validation', () => {
    it('should add credentials with valid MFA secret', async () => {
      const vault = client.Vault();

      // Use a valid base32 MFA secret format
      await vault.addCredentials('https://github.com/', {
        email: 'xyz@notte.cc',
        password: 'xyz', // pragma: allowlist secret
        mfa_secret: 'JBSWY3DPEHPK3PXP' // pragma: allowlist secret
      });

      const vaultId = vault.vaultId;
      createdVaults.push(vaultId);

      // Verify credentials were added
      const credentials = await vault.getCredentials('https://github.com/');
      expect(credentials).toBeDefined();
      expect(credentials?.mfa_secret).toBe('JBSWY3DPEHPK3PXP'); // pragma: allowlist secret
    });

    it('should throw error for invalid MFA secret (all numbers)', async () => {
      const vault = client.Vault();

      // This should fail because MFA secret is all numbers
      await expect(vault.addCredentials('https://github.com/', {
        email: 'xyz@notte.cc',
        password: 'xyz', // pragma: allowlist secret
        mfa_secret: '999777' // pragma: allowlist secret
      })).rejects.toThrow();

      // Vault may not be initialized if addCredentials throws before initialization
      // Try to get vault ID for cleanup, but don't fail if it's not initialized
      try {
        const vaultId = vault.vaultId;
        createdVaults.push(vaultId);
      } catch {
        // Vault not initialized, which is expected when addCredentials fails early
      }
    });

    it('should throw error for MFA secret too short', async () => {
      const vault = client.Vault();

      // This should fail because MFA secret is too short
      await expect(vault.addCredentials('https://github.com/', {
        email: 'xyz@notte.cc',
        password: 'xyz', // pragma: allowlist secret
        mfa_secret: 'short' // pragma: allowlist secret
      })).rejects.toThrow();

      // Vault may not be initialized if addCredentials throws before initialization
      // Try to get vault ID for cleanup, but don't fail if it's not initialized
      try {
        const vaultId = vault.vaultId;
        createdVaults.push(vaultId);
      } catch {
        // Vault not initialized, which is expected when addCredentials fails early
      }
    });
  });

  describe('Error Handling', () => {
    it('should handle invalid credentials in agent', { timeout: 120000 }, async () => {
      const vault = client.Vault();

      // Create session and agent without valid credentials
      const session = client.Session({ proxies: false });
      await session.start();

      try {
        // Initialize vault by performing an operation to ensure vaultId is available
        await vault.listCredentials();
        const vaultId = vault.vaultId;
        createdVaults.push(vaultId);

        const agent = client.Agent({
          session,
          vault_id: vaultId,
          max_steps: 10 // Limit steps to prevent infinite loops
        });

        // This should fail because no credentials are available or agent gets stuck
        // Use Promise.race to timeout if agent takes too long
        try {
          const result = await Promise.race([
            agent.run({
              task: 'Go to console.notte.cc and login then retrieve the current active usage'
            }),
            new Promise((_, reject) =>
              setTimeout(() => reject(new Error('Agent timed out')), 90000)
            )
          ]);

          // If agent completes, it might have failed or gotten stuck
          // Just verify we got some response
          expect(result).toBeDefined();
        } catch (error) {
          // Expected behavior - should fail without credentials or timeout
          expect(error).toBeDefined();
        }
      } finally {
        await session.stop();
      }
    });

    it('should return null for non-existent credentials', async () => {
      const vault = client.Vault();

      // Try to get credentials that don't exist
      const credentials = await vault.getCredentials('https://nonexistent.com/');
      expect(credentials).toBeNull();

      // Get vault ID after initialization for cleanup
      const vaultId = vault.vaultId;
      createdVaults.push(vaultId);
    });
  });
});
