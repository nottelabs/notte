// Example usage of the Vault functionality in the TypeScript SDK

import { NotteClient } from 'notte-sdk';

async function vaultExample() {
  const client = new NotteClient();

  // Example 1: Create a new vault
  console.log('=== Creating a new vault ===');
  const newVault = client.Vault({ name: 'My Secure Vault' });

  // Add credentials for different websites
  await newVault.addCredentials('https://github.com/', {
    email: 'user@example.com',
    password: 'secure-password-123', // pragma: allowlist secret
    mfa_secret: 'PYNT7I67RFS2EPR5' // pragma: allowlist secret
  });

  await newVault.addCredentials('https://gmail.com/', {
    email: 'user@gmail.com',
    password: newVault.generatePassword(16, true) // Generate secure password
  });

  // List all stored credentials
  const credentials = await newVault.listCredentials();
  console.log('Stored credentials:', credentials.map(c => c.url));

  // Get specific credentials
  const githubCreds = await newVault.getCredentials('https://github.com/');
  console.log('GitHub credentials:', githubCreds);

  // Example 2: Access existing vault
  console.log('\n=== Using existing vault ===');
  const existingVault = client.Vault({ vault_id: 'vault-abc-123' });

  try {
    const existingCreds = await existingVault.listCredentials();
    console.log('Existing vault credentials:', existingCreds);
  } catch (error) {
    console.log('Vault not found or inaccessible');
  }

  // Example 3: Password generation
  console.log('\n=== Password generation examples ===');
  console.log('Strong password (20 chars):', newVault.generatePassword());
  console.log('Medium password (12 chars):', newVault.generatePassword(12));
  console.log('No special chars (15 chars):', newVault.generatePassword(15, false));

  // Example 4: Cleanup
  console.log('\n=== Cleanup ===');

  // Delete specific credentials
  await newVault.deleteCredentials('https://gmail.com/');

  // Delete entire vault (this also stops it)
  await newVault.stop();

  console.log('Vault deleted successfully');
}

// Example of Python-like usage pattern
async function pythonLikeUsage() {
  const client = new NotteClient();

  // This mirrors the Python SDK pattern:
  // vault = notte.Vault(vault_id="my_vault_id")
  // vault.add_credentials(url="https://github.com/", email="...", password="...")

  const vault = client.Vault({ vault_id: "my_vault_id" });

  await vault.addCredentials("https://github.com/", {
    email: "my_cool_email@gmail.com",
    password: "my_cool_password", // pragma: allowlist secret
    mfa_secret: "PYNT7I67RFS2EPR5" // pragma: allowlist secret
  });

  console.log('Vault setup complete!');
}

if (require.main === module) {
  vaultExample().catch(console.error);
}
