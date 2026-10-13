// Example usage of the Persona functionality in the TypeScript SDK

import { NotteClient } from 'notte-sdk';

/**
 * Persona used by the "existing persona" examples. Set NOTTE_PERSONA_ID to the
 * id of a persona you own (see `client.personas.list()`).
 */
function requirePersonaId(): string {
  const personaId = process.env.NOTTE_PERSONA_ID;
  if (!personaId) {
    throw new Error('Set NOTTE_PERSONA_ID to the id of an existing persona to run this example');
  }
  return personaId;
}

async function personaExample() {
  // Validate the environment before creating remote resources so a missing
  // variable cannot skip the cleanup at the end of the example.
  const existingPersonaId = requirePersonaId();
  const client = new NotteClient();

  // Example 1: Try to create a new persona with a vault
  console.log('=== Creating a new persona ===');
  const persona = client.Persona({ create_vault: true });

  // Wait for persona to be created and get info
  console.log('Persona created, checking info...');
  // Initialize persona by making an async call first
  await persona.emails({ limit: 1 }); // This will trigger initialization
  const info = persona.info;
  console.log(`Email: ${info.email}`);
  console.log(`Has vault: ${persona.hasVault}`);

  // List existing personas and use one of them
  console.log('\n=== Using existing persona instead ===');
  const existingPersonas = await client.personas.list({ only_active: true });
  if (existingPersonas.length === 0) {
    throw new Error('No existing personas available and cannot create new one');
  }

  const firstPersona = existingPersonas[0];
  console.log(`Using existing persona: ${firstPersona.persona_id}`);
  const newPersona = client.Persona({ persona_id: firstPersona.persona_id });

  // Initialize and show info
  await newPersona.emails({ limit: 1 }); // This will trigger initialization
  const newInfo = newPersona.info;
  console.log(`Email: ${newInfo.email}`);
  console.log(`Has vault: ${newPersona.hasVault}`);

  // Example 2: Read emails sent to the persona
  console.log('\n=== Reading persona emails ===');
  const emails = await persona.emails({
    limit: 10,
    only_unread: true
  });
  console.log(`Received ${emails.length} new emails:`);
  emails.forEach(email => {
    console.log(`- Subject: ${email.subject}`);
    console.log(`  From: ${email.sender_email}`);
    console.log(`  Date: ${email.created_at}`);
  });

  // Example 3: Read SMS messages for 2FA codes
  console.log('\n=== Reading persona SMS messages ===');
  const smsMessages = await persona.sms({
    limit: 5,
    only_unread: true
  });
  console.log(`Received ${smsMessages.length} SMS messages:`);
  smsMessages.forEach(sms => {
    console.log(`- Body: ${sms.body}`);
    console.log(`  From: ${sms.sender}`);
    console.log(`  Date: ${sms.created_at}`);
  });

  // Example 4: Add credentials to persona's vault
  console.log('\n=== Adding credentials to vault ===');
  if (persona.hasVault) {
    await persona.addCredentials('https://github.com/');
    console.log('Credentials added to vault with auto-generated password');
  }
  // Example 5: Use persona with agent for automated account creation
  console.log('\n=== Using persona with Agent ===');
  if (persona.hasVault) {
    try {
      await client.Session().use(async (session) => {
        const agent = client.Agent({
          session,
          max_steps: 10,
          vault_id: persona.vault.vaultId // Use the persona's vault
        });

        const result = await agent.run({
          task: "Create an account on GitHub using the persona credentials",
          url: "https://github.com/login"
        });
        console.log(`Account created: ${result.success ? 'Success' : 'Failed'}`);
        console.log(`Result: ${result.answer}`);
      });
    } catch (error) {
      console.log('Agent task failed:', error instanceof Error ? error.message : String(error));
    }
  } else {
    console.log('Persona has no vault, skipping agent example with credentials');
  }

  // Example 6: Access an existing persona by id
  console.log('\n=== Using existing persona ===');
  const existingPersona = client.Persona({ persona_id: existingPersonaId });

  const existingEmails = await existingPersona.emails();
  console.log(`Existing persona has ${existingEmails.length} emails`);

  // Example 7: Cleanup (only if we created a new persona)
  console.log('\n=== Cleanup ===');
  console.log('Deleting the persona created by this example. Borrowed personas are left untouched.');
  await persona.delete();
}

// Example of Python-like usage pattern
async function pythonLikeUsage() {
  const client = new NotteClient();

  // This mirrors the Python SDK pattern:
  // persona = notte.Persona(create_vault=True)
  // emails = persona.emails(only_unread=True)

  const persona = client.Persona({ create_vault: true });

  const emails = await persona.emails({ only_unread: true });
  const sms = await persona.sms({ limit: 10 });

  // After making async calls, persona is initialized and personaId is available
  console.log(`Persona ${persona.personaId} ready with ${emails.length} emails and ${sms.length} SMS`);

  // Use personas client directly for advanced operations
  const allPersonas = await client.personas.list({ only_active: true });
  console.log(`Total active personas: ${allPersonas.length}`);
}

// Example showing message filtering options
async function messageFilteringExample() {
  const client = new NotteClient();

  const persona = client.Persona({ persona_id: requirePersonaId() });

  // Different filtering options
  console.log('=== Message filtering examples ===');

  // Get all emails from last hour
  const recentEmails = await persona.emails({
    timedelta: '1h',
    only_unread: false
  });
  console.log(`Emails from last hour: ${recentEmails.length}`);

  // Get only unread SMS messages, limit to 5
  const unreadSms = await persona.sms({
    only_unread: true,
    limit: 5
  });
  console.log(`Unread SMS messages: ${unreadSms.length}`);

  // Get all emails from last 24 hours
  const dailyEmails = await persona.emails({
    timedelta: '24h'
  });
  console.log(`Emails from last 24 hours: ${dailyEmails.length}`);
}

if (require.main === module) {
  personaExample().catch(console.error);
}

export { personaExample, pythonLikeUsage, messageFilteringExample };
