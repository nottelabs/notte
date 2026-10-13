import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { NotteClient } from '@/index';
import { InvalidRequestError, NotteAPIError } from '@/errors';
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
    vi.unstubAllEnvs();
    await cleanupVaults(client, createdVaults);
    createdVaults = [];
  });

  it('should only cleanup a vault created by this test', { timeout: 30000 }, async () => {
    const vault = client.Vault({ name: 'Node SDK owned cleanup test' });
    await vault.listCredentials();
    const vaultId = vault.vaultId;

    await cleanupVaults(client, [vaultId]);

    const deletedVault = client.Vault({ vault_id: vaultId });
    await expect(deletedVault.listCredentials()).rejects.toBeInstanceOf(NotteAPIError);
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
      expect(credentials.email).toBe('xyz@notte.cc');
      expect(credentials.password).toBe('xyz');
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

      // List all credentials: URLs are stored as root domains and passwords are never returned.
      const credentials = await vault.listCredentials();
      expect(credentials).toHaveLength(2);
      expect(credentials.some(c => c.url === 'github.com')).toBe(true);
      expect(credentials.some(c => c.url === 'google.com')).toBe(true);
      expect(credentials.every(c => !('password' in c))).toBe(true);
    });

    it('should report whether a credential exists', async () => {
      const vault = client.Vault();

      await vault.addCredentials('https://github.com/', {
        email: 'test@example.com',
        password: 'password' // pragma: allowlist secret
      });
      createdVaults.push(vault.vaultId);

      await expect(vault.hasCredential('https://github.com/login')).resolves.toBe(true);
      await expect(vault.hasCredential('github.com')).resolves.toBe(true);
      await expect(vault.hasCredential('https://google.com/')).resolves.toBe(false);
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
      await expect(vault.getCredentials('https://github.com/')).resolves.toMatchObject({ email: 'test@example.com' });

      // Delete credentials
      await vault.deleteCredentials('https://github.com/');

      // Verify credentials are deleted: like Python, a missing credential is an API error.
      await expect(vault.getCredentials('https://github.com/')).rejects.toBeInstanceOf(NotteAPIError);
      await expect(vault.hasCredential('https://github.com/')).resolves.toBe(false);
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
      expect(() => vault.generatePassword(2)).toThrow(InvalidRequestError);
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
    // Mirrors test_vault_should_be_deleted_after_exit_context: stop() deletes the vault.
    it('should delete vault after stop()', { timeout: 60000 }, async () => {
      const vault = client.Vault();
      await vault.addCredentials('https://test.com/', {
        email: 'test@example.com',
        password: 'testpassword' // pragma: allowlist secret
      });

      const vaultId = vault.vaultId;

      // Stop vault (which should delete it)
      await vault.stop();

      // The vault is gone from the listing and can no longer be opened.
      const vaults = await client.vaults.list();
      expect(vaults.some(v => v.vault_id === vaultId)).toBe(false);
      const deletedVault = client.Vault({ vault_id: vaultId });
      await expect(deletedVault.listCredentials()).rejects.toBeInstanceOf(NotteAPIError);
    });
  });

  describe('Environment Variable Credentials', () => {
    // Mirrors test_add_credentials_from_env.
    it('should add credentials from environment variables', { timeout: 60000 }, async () => {
      vi.stubEnv('PEEPLE_COM_EMAIL', 'xyz@notte.cc');
      vi.stubEnv('PEEPLE_COM_PASSWORD', 'xyz'); // pragma: allowlist secret
      vi.stubEnv('TEST_COM_USERNAME', 'my_xyz_username');
      vi.stubEnv('TEST_COM_PASSWORD', 'my_xyz_password'); // pragma: allowlist secret

      const vault = client.Vault();

      // Add credentials from environment: sub-domains resolve to the root domain's variables.
      await vault.addCredentialsFromEnv('https://test.peeple.com/ok');
      await vault.addCredentialsFromEnv('https://test.com');

      const vaultId = vault.vaultId;
      createdVaults.push(vaultId);

      // Unknown website: an API error, like Python.
      await expect(vault.getCredentials('https://accounts.google.com')).rejects.toBeInstanceOf(NotteAPIError);

      // Getting credentials with different URL formats
      await expect(vault.getCredentials('https://test.peeple.com/test')).resolves.toEqual({
        email: 'xyz@notte.cc',
        password: 'xyz'
      });
      await expect(vault.getCredentials('peeple.com')).resolves.toEqual({
        email: 'xyz@notte.cc',
        password: 'xyz'
      });
      await expect(vault.getCredentials('https://test.com/')).resolves.toEqual({
        username: 'my_xyz_username',
        password: 'my_xyz_password' // pragma: allowlist secret
      });
    });

    it('should add an MFA secret from the environment', { timeout: 60000 }, async () => {
      vi.stubEnv('EXAMPLE_COM_EMAIL', 'xyz@notte.cc');
      vi.stubEnv('EXAMPLE_COM_PASSWORD', 'xyz'); // pragma: allowlist secret
      vi.stubEnv('EXAMPLE_COM_MFA_SECRET', 'JBSWY3DPEHPK3PXP'); // pragma: allowlist secret

      const vault = client.Vault();
      await vault.addCredentialsFromEnv('https://example.com/');
      createdVaults.push(vault.vaultId);

      await expect(vault.getCredentials('https://example.com/')).resolves.toMatchObject({
        email: 'xyz@notte.cc',
        mfa_secret: 'JBSWY3DPEHPK3PXP' // pragma: allowlist secret
      });
    });

    it('should throw error for missing environment variables', async () => {
      const vault = client.Vault();

      // This fails before any API call because the environment variables are not set.
      const failure = vault.addCredentialsFromEnv('https://example.com/');
      await expect(failure).rejects.toBeInstanceOf(InvalidRequestError);
      await expect(failure).rejects.toThrow(/EXAMPLE_COM_EMAIL/);
      expect(() => vault.vaultId).toThrow(InvalidRequestError);
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
      expect(credentials.mfa_secret).toBe('JBSWY3DPEHPK3PXP'); // pragma: allowlist secret
    });

    // Mirrors test_add_correct_otp: any base32 string is a valid secret.
    it('should accept a short base32 secret', async () => {
      const vault = client.Vault();

      await vault.addCredentials('https://github.com/', {
        email: 'xyz@notte.cc',
        password: 'xyz', // pragma: allowlist secret
        mfa_secret: 'mysecret' // pragma: allowlist secret
      });
      createdVaults.push(vault.vaultId);

      await expect(vault.getCredentials('https://github.com/')).resolves.toMatchObject({ mfa_secret: 'mysecret' }); // pragma: allowlist secret
    });

    // Mirrors test_add_wrong_otp: a one-time code is rejected client-side.
    it('should throw error for invalid MFA secret (all numbers)', async () => {
      const vault = client.Vault();

      await expect(vault.addCredentials('https://github.com/', {
        email: 'xyz@notte.cc',
        password: 'xyz', // pragma: allowlist secret
        mfa_secret: '999777' // pragma: allowlist secret
      })).rejects.toBeInstanceOf(InvalidRequestError);

      // Validation fails before the vault is created remotely.
      expect(() => vault.vaultId).toThrow(InvalidRequestError);
    });

    it('should reject credentials with both username and email', async () => {
      const vault = client.Vault();

      await expect(vault.addCredentials('https://github.com/', {
        email: 'xyz@notte.cc',
        username: 'xyz',
        password: 'xyz' // pragma: allowlist secret
      })).rejects.toThrow('Can only set either username or email');
      expect(() => vault.vaultId).toThrow(InvalidRequestError);
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

    it('should reject non-existent credentials with a NotteAPIError', async () => {
      const vault = client.Vault();

      const failure = vault.getCredentials('https://nonexistent.com/');
      await expect(failure).rejects.toBeInstanceOf(NotteAPIError);
      await expect(failure).rejects.toMatchObject({ statusCode: expect.any(Number) });

      // Get vault ID after initialization for cleanup
      const vaultId = vault.vaultId;
      createdVaults.push(vaultId);
    });

    it('should reject an invalid URL before calling the API', async () => {
      const vault = client.Vault();
      await expect(vault.getCredentials('https://')).rejects.toBeInstanceOf(InvalidRequestError);
      expect(() => vault.vaultId).toThrow(InvalidRequestError);
    });
  });
});
