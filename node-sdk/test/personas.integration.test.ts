import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { NotteClient, NottePersona } from '@/index';
import { Session } from '@/session';
import { Agent } from '@/agent';
import { config } from 'dotenv';

// Load environment variables from .env file
config();

// Load environment variables
const API_KEY = process.env.NOTTE_API_KEY;

describe('Persona Integration Tests', () => {
  let client: NotteClient;
  let fixturePersona: NottePersona | undefined;

  async function existingPersona() {
    fixturePersona = client.Persona({ create_phone_number: false });
    await fixturePersona.get();
    return client.Persona({ persona_id: fixturePersona.personaId });
  }

  afterEach(async () => {
    if (fixturePersona) await fixturePersona.delete();
    fixturePersona = undefined;
  });

  beforeEach(() => {
    if (!API_KEY) {
      throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
    }
    client = new NotteClient({ apiKey: API_KEY });
  });

  describe.sequential('Basic Persona Operations', () => {
    // Run tests sequentially to avoid concurrency limits
    it('should handle persona creation limits', async () => {
      // Try to create a new persona
      const persona = client.Persona();
      let personaId: string | null = null;

      try {
        await persona.get();
        personaId = persona.personaId;

        // Verify persona was created
        expect(personaId).toBeDefined();
        expect(persona.info).toBeDefined();
        expect(persona.info?.status).toBe('active');
        expect(persona.info?.first_name).toBeDefined();
        expect(persona.info?.last_name).toBeDefined();
        expect(persona.info?.email).toBeDefined();
      } catch (error) {
        // If persona limit is reached, that's expected - just verify the error
        expect((error as Error).message).toContain('Max active personas limit exceeded');
      } finally {
        // Clean up in the same test
        if (personaId) {
          try {
            await client.Persona({ persona_id: personaId }).delete();
          } catch (error) {
            console.warn(`Failed to delete persona ${personaId} during cleanup: ${error}`);
          }
        }
      }
    });

    it('should delete persona', async () => {
      // Create a persona for deletion test
      const persona = client.Persona();
      let personaId: string | null = null;

      try {
        await persona.get();
        personaId = persona.personaId;

        // Verify persona exists
        const retrievedPersona = client.Persona({ persona_id: personaId });
        await retrievedPersona.get();
        expect(retrievedPersona.personaId).toBe(personaId);

        // Delete persona
        const deleteResponse = await persona.delete();
        expect(deleteResponse.status).toBe('success');
        expect(deleteResponse.message).toBe('Persona deleted successfully');
        const deletedPersonaId = personaId; // Save ID before clearing
        personaId = null; // Mark as deleted so we don't try to delete again

        // Verify persona is deleted
        try {
          await client.Persona({ persona_id: deletedPersonaId! }).get();
          expect.fail('Expected persona to be deleted');
        } catch (error) {
          expect(error).toBeDefined();
        }
      } catch (error) {
        // If we can't create a persona, fail the test (don't skip)
        throw error;
      } finally {
        // Clean up if persona still exists
        if (personaId) {
          try {
            await client.Persona({ persona_id: personaId }).delete();
          } catch (error) {
            console.warn(`Failed to delete persona ${personaId} during cleanup: ${error}`);
          }
        }
      }
    });
    it('should get existing persona by ID', async () => {
      const persona = await existingPersona();
      const testPersonaId = fixturePersona!.personaId;

      // Initialize the persona
      await persona.get();

      // Verify persona was retrieved
      expect(persona.personaId).toBe(testPersonaId);
      expect(persona.info).toBeDefined();
      expect(persona.info?.status).toBe('active');
      expect(persona.info?.first_name).toBeDefined();
      expect(persona.info?.last_name).toBeDefined();
      expect(persona.info?.email).toBeDefined();
    });

  });

  describe.sequential('Persona Context Manager', () => {
    it('should delete persona after context exit', async () => {
      let personaId: string | null = null;

      try {
        await client.Persona().use(async (persona) => {
          await persona.get(); // Initialize the persona
          personaId = persona.personaId;
          expect(personaId).toBeDefined();
          expect(persona.info).toBeDefined();
          expect(persona.personaId).toBe(personaId);
        });

        // Verify persona is deleted after context exit
        expect(personaId).toBeDefined();
        try {
          await client.Persona({ persona_id: personaId! }).get();
          expect.fail('Expected persona to be deleted after context exit');
        } catch (error) {
          expect(error).toBeDefined();
        }
      } catch (error) {
        // If persona creation fails, fail the test (don't skip)
        throw error;
      } finally {
        // Clean up if persona still exists (shouldn't happen with use(), but just in case)
        if (personaId) {
          try {
            await client.Persona({ persona_id: personaId }).delete();
          } catch (error) {
            // Ignore - persona might already be deleted by use()
          }
        }
      }
    });

    it('should work with existing persona ID', async () => {
      // Create persona first
      const createdPersona = client.Persona();
      let personaId: string | null = null;

      try {
        await createdPersona.get();
        personaId = createdPersona.personaId;

        // Use persona with existing ID (should not delete it since it was created outside context)
        await client.Persona({ persona_id: personaId }).use(async (persona) => {
          await persona.get();
          expect(persona.personaId).toBe(personaId);
          expect(persona.info).toBeDefined();
        });
      } catch (error) {
        // If persona creation fails, fail the test (don't skip)
        throw error;
      } finally {
        // Clean up in the same test
        if (personaId) {
          try {
            await client.Persona({ persona_id: personaId }).delete();
          } catch (error) {
            console.warn(`Failed to delete persona ${personaId} during cleanup: ${error}`);
          }
        }
      }
    });
  });

  describe.sequential('Persona with Vault Integration', () => {
    it('should create persona with vault', { timeout: 30000 }, async () => {
      const persona = client.Persona({ create_vault: true });
      let personaId: string | null = null;

      try {
        await persona.get();
        personaId = persona.personaId;

        // Verify persona has vault
        expect(persona.info?.vault_id).toBeDefined();
        expect(persona.info?.status).toBe('active');
        expect(persona.info?.phone_number).toBeNull();

        // Test vault access - need to initialize vault first
        const vault = persona.vault;
        // Initialize vault by performing an operation
        await vault.listCredentials();
        expect(vault.vaultId).toBe(persona.info?.vault_id);

        // Add credentials to vault
        await vault.addCredentials('https://test.com', {
          email: persona.info?.email || 'test@example.com',
          password: 'testpassword' // pragma: allowlist secret
        });

        // Verify credentials were added
        const credentials = await vault.getCredentials('https://test.com');
        expect(credentials).toBeDefined();
        expect(credentials?.email).toBe(persona.info?.email);
      } catch (error) {
        // If persona creation fails, fail the test (don't skip)
        throw error;
      } finally {
        // Clean up in the same test
        if (personaId) {
          try {
            await client.Persona({ persona_id: personaId }).delete();
          } catch (error) {
            console.warn(`Failed to delete persona ${personaId} during cleanup: ${error}`);
          }
        }
      }
    });

    it('should handle persona without vault access', async () => {
      const persona = client.Persona();
      let personaId: string | null = null;

      try {
        await persona.get();
        personaId = persona.personaId;

        // Verify persona has no vault
        expect(persona.info?.vault_id).toBeNull();

        // Try to access vault should throw error
        try {
          const vault = persona.vault;
          expect.fail('Expected error when accessing vault for persona without vault');
        } catch (error) {
          expect(error).toBeDefined();
          expect((error as Error).message).toContain('Persona has no vault');
        }
      } catch (error) {
        // If persona creation fails, fail the test (don't skip)
        throw error;
      } finally {
        // Clean up in the same test
        if (personaId) {
          try {
            await client.Persona({ persona_id: personaId }).delete();
          } catch (error) {
            console.warn(`Failed to delete persona ${personaId} during cleanup: ${error}`);
          }
        }
      }
    });

    it('should handle vault email restrictions', { timeout: 30000 }, async () => {
      const persona = client.Persona({ create_vault: true });
      let personaId: string | null = null;

      try {
        await persona.get();
        personaId = persona.personaId;

        const vault = persona.vault;

        // Try to add credentials with different email should fail
        try {
          await vault.addCredentials('https://github.com/', {
            email: 'different@example.com',
            password: 'password' // pragma: allowlist secret
          });
          expect.fail('Expected error when adding credentials with different email');
        } catch (error) {
          expect(error).toBeDefined();
          expect((error as Error).message).toContain('This vault can only store one email address');
        }

        // Add credentials with persona's email should work
        await vault.addCredentials('https://github.com/', {
          email: persona.info?.email || 'test@example.com',
          password: 'password' // pragma: allowlist secret
        });

        // Verify credentials were added
        const credentials = await vault.getCredentials('https://github.com/');
        expect(credentials).toBeDefined();
        expect(credentials?.email).toBe(persona.info?.email);
      } catch (error) {
        // If persona creation fails, fail the test (don't skip)
        throw error;
      } finally {
        // Clean up in the same test
        if (personaId) {
          try {
            await client.Persona({ persona_id: personaId }).delete();
          } catch (error) {
            console.warn(`Failed to delete persona ${personaId} during cleanup: ${error}`);
          }
        }
      }
    });
  });

  describe.sequential('Persona with Agent Integration', () => {
    it('should let a local agent read persona email', async () => {
      const persona = client.Persona({ create_vault: true });
      let personaId: string | null = null;
      const session = client.Session({ proxies: false });

      try {
        await persona.get();
        personaId = persona.personaId;

        await session.start();

        const agent = client.Agent({
          session,
          max_steps: 3,
          persona
        });
        const actionNames: string[] = [];

        try {
          const result = await agent.run({
            task: 'Call email_read now to check the persona inbox. Do not navigate to a website. Then immediately complete with a short summary.',
            updateHandler: (update) => {
              if (update.type !== 'step') {
                return;
              }

              const actionName = update.data?.action?.name ?? update.data?.action?.type;
              if (typeof actionName === 'string') {
                actionNames.push(actionName);
              }
            }
          });

          expect(result.status).toBe('closed');
          expect(result.success).toBe(true);
          expect(result.session_id).toBe(session.getId());
          expect(actionNames).toContain('email_read');
          expect(agent.agentId).toBe(result.agent_id);
        } finally {
          await session.stop();
        }
      } catch (error) {
        // If persona creation fails, fail the test (don't skip)
        throw error;
      } finally {
        // Clean up in the same test
        if (personaId) {
          try {
            await client.Persona({ persona_id: personaId }).delete();
          } catch (error) {
            console.warn(`Failed to delete persona ${personaId} during cleanup: ${error}`);
          }
        }
      }
    }, 60000);

    it('should use persona with remote agent', async () => {
      const persona = client.Persona({ create_vault: true });
      let personaId: string | null = null;
      const session = client.Session({ proxies: false, headless: true });

      try {
        await persona.get();
        personaId = persona.personaId;

        // Add credentials to persona's vault
        await persona.vault.addCredentials('https://github.com/', {
          email: persona.info?.email || 'test@example.com',
          password: 'password' // pragma: allowlist secret
        });

        // Create session and agent
        await session.start();

        try {
          const agent = client.Agent({
            session,
            max_steps: 1,
            persona
          });

          // Run agent task
          const result = await agent.run({
            task: "Try to login to github.com with the persona's credentials"
          });

          expect(result).toBeDefined();
          // The result should be a LegacyAgentStatusResponse
          if (result && typeof result === 'object' && 'success' in result) {
            expect(result.success).toBeDefined();
          } else {
            // If result doesn't have expected structure, at least verify agent was created
            expect(agent.agentId).toBeDefined();
          }
        } finally {
          await session.stop();
        }
      } catch (error) {
        // If persona creation fails, fail the test (don't skip)
        throw error;
      } finally {
        // Clean up in the same test
        if (personaId) {
          try {
            await client.Persona({ persona_id: personaId }).delete();
          } catch (error) {
            console.warn(`Failed to delete persona ${personaId} during cleanup: ${error}`);
          }
        }
      }
    }, 30000); // 30 second timeout
  });

  describe('Email and SMS Operations', () => {
    it('should read emails with filters', async () => {
      const persona = await existingPersona();

      // Test reading emails with different filters
      const allEmails = await persona.emails();
      expect(allEmails).toEqual([]);

      // Test with limit
      const limitedEmails = await persona.emails({ limit: 5 });
      expect(limitedEmails).toEqual([]);

      // Test with unread only
      const unreadEmails = await persona.emails({ only_unread: true });
      expect(unreadEmails.length).toBeGreaterThanOrEqual(0);
    });

    it('should reject SMS filters for a persona without a phone', async () => {
      const persona = await existingPersona();
      // Do not allocate a billable phone or depend on a shared inbox in CI.
      for (const filter of [undefined, { limit: 5 }, { only_unread: true }]) {
        await expect(persona.sms(filter)).rejects.toThrow(/phone/i);
      }
    });

    it('should handle empty email and SMS for new persona', async () => {
      // Create a new persona for testing
      const persona = client.Persona();
      let personaId: string | null = null;

      try {
        await persona.get();
        personaId = persona.personaId;

        // Test reading emails (should be empty initially)
        const emails = await persona.emails();
        expect(emails.length).toBe(0);

        // Test reading SMS (should be empty initially, but only if persona has phone number)
        if (persona.info?.phone_number) {
          const sms = await persona.sms();
          expect(sms.length).toBe(0);
        } else {
          // If persona doesn't have phone number, trying to read SMS should fail
          try {
            await persona.sms();
            expect.fail('Expected error when reading SMS for persona without phone number');
          } catch (error) {
            expect(error).toBeDefined();
          }
        }
      } catch (error) {
        // If persona creation fails, fail the test (don't skip)
        throw error;
      } finally {
        // Clean up in the same test
        if (personaId) {
          try {
            await client.Persona({ persona_id: personaId }).delete();
          } catch (error) {
            console.warn(`Failed to delete persona ${personaId} during cleanup: ${error}`);
          }
        }
      }
    });
  });

  describe('Error Handling', () => {
    it('should handle non-existent persona operations', async () => {
      const nonExistentId = 'non-existent-persona-id';

      // Try to get non-existent persona
      try {
        await client.Persona({ persona_id: nonExistentId }).get();
        expect.fail('Expected error when getting non-existent persona');
      } catch (error) {
        expect(error).toBeDefined();
      }

      // Try to delete non-existent persona
      try {
        await client.Persona({ persona_id: nonExistentId }).delete();
        expect.fail('Expected error when deleting non-existent persona');
      } catch (error) {
        expect(error).toBeDefined();
      }

      // Try to list emails for non-existent persona
      try {
        await client.Persona({ persona_id: nonExistentId }).emails();
        expect.fail('Expected error when listing emails for non-existent persona');
      } catch (error) {
        expect(error).toBeDefined();
      }

      // Try to list SMS for non-existent persona
      try {
        await client.Persona({ persona_id: nonExistentId }).sms();
        expect.fail('Expected error when listing SMS for non-existent persona');
      } catch (error) {
        expect(error).toBeDefined();
      }
    });
  });

  describe.sequential('Form Filling Integration', () => {
    it('should fill form with persona information', async () => {
      const persona = client.Persona({ create_vault: false, create_phone_number: false });
      let personaId: string | null = null;
      const session = client.Session({
        proxies: false,
        browser_type: 'chromium',
        viewport_width: 1280,
        viewport_height: 1080,
        headless: true
      });

      try {
        await persona.get();
        personaId = persona.personaId;

        await session.start();

        try {
          const agent = client.Agent({
            session,
            max_steps: 5,
            persona
          });

          const response = await agent.run({
            task: "Open the Google form and fill your name.\nDon't fill the form completely. Simply stop once you filled your name. Return your name.",
            url: "https://docs.google.com/forms/d/e/1FAIpQLScjj4EZm-Iz68RrRiv6Gf_K5PhS1Z9d34YRYr5t-sjwDtMOtQ/viewform?usp=dialog"
          });

          expect(response).toBeDefined();
          // The response should be a LegacyAgentStatusResponse
          if (response && typeof response === 'object' && 'success' in response) {
            expect(response.success).toBeDefined();
            if (response.success !== null && response.success !== undefined) {
              expect(response.success).toBe(true);
            }
            if (response.answer) {
              expect(persona.info?.first_name).toBeDefined();
              expect(persona.info?.last_name).toBeDefined();
              expect(response.answer).toContain(persona.info?.first_name || '');
              expect(response.answer).toContain(persona.info?.last_name || '');
            }
          } else {
            // If response doesn't have expected structure, at least verify agent was created
            expect(agent.agentId).toBeDefined();
          }
        } finally {
          await session.stop();
        }
      } catch (error) {
        // If persona creation fails, fail the test (don't skip)
        throw error;
      } finally {
        // Clean up in the same test
        if (personaId) {
          try {
            await client.Persona({ persona_id: personaId }).delete();
          } catch (error) {
            console.warn(`Failed to delete persona ${personaId} during cleanup: ${error}`);
          }
        }
      }
    }, 60000); // 60 second timeout for form filling
  });

});
