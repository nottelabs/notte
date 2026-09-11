import { NotteClient } from '@/client';
import type {
  Vault,
  VaultCreateRequest,
  GetCredentialsResponse,
  DeleteCredentialsResponse,
  GetCreditCardResponse,
  DeleteVaultResponse,
  ListCredentialsResponse,
  CredentialsDictInput,
  CreditCardDictInput,
  Credential
} from '@/lib/client/types.gen';
import {
  vaultCreate,
  vaultCredentialsAdd,
  vaultCredentialsGet,
  vaultCredentialsDelete,
  vaultDelete,
  vaultCredentialsList,
  vaultCreditCardSet,
  vaultCreditCardGet,
  vaultCreditCardDelete
} from '@/lib/client/sdk.gen';
import { formatError } from '@/utils';

// Constructor overloads for NotteVault - mirrors Python overloads
export interface VaultConstructorWithId {
  vault_id: string;
}

export interface VaultConstructorCreate extends Omit<VaultCreateRequest, never> {
  vault_id?: never;
}

export type VaultConstructor = VaultConstructorWithId | VaultConstructorCreate;

/**
 * Vault that fetches credentials stored using the SDK - mirrors Python NotteVault class
 */
export class NotteVault {
  private client: NotteClient;
  private _vaultId: string | null = null;
  private initPromise: Promise<string> | null = null;
  private createData: VaultCreateRequest | null = null;

  constructor(client: NotteClient, options: VaultConstructor = {}) {
    this.client = client;

    if (options && 'vault_id' in options && options.vault_id) {
      // Constructor for existing vault
      this.initPromise = this.initExistingVault(options.vault_id);
    } else {
      // Defer remote creation until an operation actually needs a vault. This
      // keeps local-only helpers such as generatePassword() side-effect free.
      this.createData = (options || {}) as VaultConstructorCreate;
    }
  }

  private async initExistingVault(vaultId: string): Promise<string> {
    // Verify vault exists by trying to list its credentials
    await this.verifyVaultExists(vaultId);
    this._vaultId = vaultId;
    return this._vaultId;
  }

  private async initNewVault(createData: VaultCreateRequest): Promise<string> {
    const response = await vaultCreate({
      client: this.client.getClient(),
      body: createData
    });

    if (response?.error) {
      throw new Error(`Failed to create vault: ${formatError(response.error)}`);
    }

    const vault = response.data as Vault;
    console.warn(`[Vault] ${vault.vault_id} created since no vault id was provided. Please store this to retrieve it later.`);
    this._vaultId = vault.vault_id;
    return this._vaultId;
  }

  private async verifyVaultExists(vaultId: string): Promise<void> {
    if (vaultId.length === 0) {
      throw new Error('Vault ID cannot be empty');
    }

    // Verify vault exists by trying to list its credentials
    const response = await vaultCredentialsList({
      client: this.client.getClient(),
      path: {
        vault_id: vaultId
      }
    });

    if (response?.error) {
      throw new Error(`Failed to verify vault exists: ${formatError(response.error)}`);
    }
  }

  private async ensureInitialized(): Promise<string> {
    if (this._vaultId) {
      return this._vaultId;
    }
    if (this.initPromise) {
      return await this.initPromise;
    }
    if (this.createData) {
      const createData = this.createData;
      this.createData = null;
      this.initPromise = this.initNewVault(createData);
      return await this.initPromise;
    }
    throw new Error('Vault not initialized');
  }

  get vaultId(): string {
    if (!this._vaultId) {
      throw new Error('Vault not initialized. Use await on vault operations first.');
    }
    return this._vaultId;
  }

  /**
   * Start the vault - no-op for compatibility with Python interface
   */
  start(): void {
    // No-op - vault is ready to use immediately
  }

  /**
   * Stop the vault - deletes it and all credentials
   */
  async stop(): Promise<void> {
    const vaultId = await this.ensureInitialized();
    console.log(`[Vault] ${vaultId} deleted. All credentials have been deleted.`);
    await this.delete();
  }

  /**
   * Add or update credentials for a URL
   */
  async addCredentials(url: string, credentials: CredentialsDictInput): Promise<void> {
    // Validate MFA secret if provided
    if (credentials.mfa_secret) {
      this.validateMfaSecret(credentials.mfa_secret);
    }

    const vaultId = await this.ensureInitialized();
    const response = await vaultCredentialsAdd({
      client: this.client.getClient(),
      path: {
        vault_id: vaultId
      },
      body: { url, credentials }
    });

    if (response?.error) {
      throw new Error(`Failed to add credentials: ${formatError(response.error)}`);
    }
  }

  /**
   * Get credentials for a URL
   */
  async getCredentials(url: string): Promise<CredentialsDictInput | null> {
    try {
      const vaultId = await this.ensureInitialized();
      const response = await vaultCredentialsGet({
        client: this.client.getClient(),
        path: {
          vault_id: vaultId
        },
        query: { url }
      });

      if (response?.error) {
        return null;
      }

      const credentialsResponse = response.data as GetCredentialsResponse;
      return credentialsResponse.credentials;
    } catch (error) {
      return null;
    }
  }

  /**
   * Delete credentials for a URL
   */
  async deleteCredentials(url: string): Promise<void> {
    const vaultId = await this.ensureInitialized();
    const response = await vaultCredentialsDelete({
      client: this.client.getClient(),
      path: {
        vault_id: vaultId
      },
      query: { url }
    });

    if (response?.error) {
      throw new Error(`Failed to delete credentials: ${formatError(response.error)}`);
    }
  }

  /**
   * Set credit card information
   */
  async setCreditCard(creditCard: CreditCardDictInput): Promise<void> {
    const vaultId = await this.ensureInitialized();
    const response = await vaultCreditCardSet({
      client: this.client.getClient(),
      path: {
        vault_id: vaultId
      },
      body: { credit_card: creditCard }
    });

    if (response?.error) {
      throw new Error(`Failed to set credit card: ${formatError(response.error)}`);
    }
  }

  /**
   * Get credit card information
   */
  async getCreditCard(): Promise<CreditCardDictInput> {
    const vaultId = await this.ensureInitialized();
    const response = await vaultCreditCardGet({
      client: this.client.getClient(),
      path: {
        vault_id: vaultId
      }
    });

    if (response?.error) {
      throw new Error(`Failed to get credit card: ${formatError(response.error)}`);
    }

    const creditCardResponse = response.data as GetCreditCardResponse;
    return creditCardResponse.credit_card;
  }

  /**
   * List all credentials in the vault
   */
  async listCredentials(): Promise<Credential[]> {
    const vaultId = await this.ensureInitialized();
    const response = await vaultCredentialsList({
      client: this.client.getClient(),
      path: {
        vault_id: vaultId
      }
    });

    if (response?.error) {
      throw new Error(`Failed to list credentials: ${formatError(response.error)}`);
    }

    const credentialsResponse = response.data as ListCredentialsResponse;
    return credentialsResponse.credentials;
  }

  /**
   * Delete credit card information
   */
  async deleteCreditCard(): Promise<void> {
    const vaultId = await this.ensureInitialized();
    const response = await vaultCreditCardDelete({
      client: this.client.getClient(),
      path: {
        vault_id: vaultId
      }
    });

    if (response?.error) {
      throw new Error(`Failed to delete credit card: ${formatError(response.error)}`);
    }
  }

  /**
   * Delete the entire vault
   */
  async delete(): Promise<void> {
    const vaultId = await this.ensureInitialized();
    const response = await vaultDelete({
      client: this.client.getClient(),
      path: {
        vault_id: vaultId
      }
    });

    if (response?.error) {
      throw new Error(`Failed to delete vault: ${formatError(response.error)}`);
    }
  }

  /**
   * Add credentials from environment variables
   * Mirrors Python's add_credentials_from_env method
   */
  async addCredentialsFromEnv(url: string): Promise<void> {
    // Extract domain from URL for environment variable naming
    const domain = this.extractDomainFromUrl(url);
    const envPrefix = domain.replace(/[^a-zA-Z0-9]/g, '_').toUpperCase();

    // Look for common credential environment variables
    const email = process.env[`${envPrefix}_EMAIL`] || process.env[`${envPrefix}_USERNAME`];
    const password = process.env[`${envPrefix}_PASSWORD`];

    if (!email || !password) {
      throw new Error(`Environment variables ${envPrefix}_EMAIL/USERNAME and ${envPrefix}_PASSWORD are required`);
    }

    const credentials: CredentialsDictInput = { email, password };

    // Add MFA secret if available
    const mfaSecret = process.env[`${envPrefix}_MFA_SECRET`];
    if (mfaSecret) {
      this.validateMfaSecret(mfaSecret);
      credentials.mfa_secret = mfaSecret;
    }

    await this.addCredentials(url, credentials);
  }

  /**
   * Extract domain from URL for environment variable naming
   */
  private extractDomainFromUrl(url: string): string {
    try {
      const urlObj = new URL(url);
      return urlObj.hostname.replace(/^www\./, '');
    } catch {
      // If URL parsing fails, try to extract domain manually
      const match = url.match(/(?:https?:\/\/)?(?:www\.)?([^\/]+)/);
      return match ? match[1] : url;
    }
  }

  /**
   * Validate MFA secret format
   * Mirrors Python's MFA secret validation
   */
  private validateMfaSecret(mfaSecret: string): void {
    // MFA secret should be a valid base32 string (typically 16-32 characters)
    // and should not be all numbers (which would be invalid)
    if (/^\d+$/.test(mfaSecret)) {
      throw new Error('MFA secret cannot be all numbers. Please provide a valid base32 secret.');
    }

    if (mfaSecret.length < 16) {
      throw new Error('MFA secret must be at least 16 characters long');
    }
  }

  /**
   * Generate a secure random password
   * Mirrors Python's generate_password method
   */
  generatePassword(length: number = 20, includeSpecialChars: boolean = true): string {
    // Validate minimum length
    const minRequiredLength = includeSpecialChars ? 4 : 3;
    if (length < minRequiredLength) {
      throw new Error(`Password length must be at least ${minRequiredLength} characters`);
    }

    // Character sets
    const lowercase = 'abcdefghijklmnopqrstuvwxyz';
    const uppercase = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    const digits = '0123456789';
    const specialChars = '!@#$%^&*()_+-=[]|;:,.<>?';

    // Generate initial random password using crypto
    const crypto = globalThis.crypto || require('crypto');
    const array = new Uint8Array(length);
    crypto.getRandomValues(array);

    // Use appropriate character set based on includeSpecialChars
    const allowedChars = includeSpecialChars
      ? 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' // pragma: allowlist secret
      : 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let password = Array.from(array, byte => allowedChars[byte % allowedChars.length]).join('').slice(0, length);
    const passwordArray = password.split('');

    // Ensure we have required character types by replacing some characters
    // This maintains randomness while guaranteeing complexity requirements

    // If special chars are not allowed, remove any that might have been included first
    if (!includeSpecialChars) {
      for (let i = 0; i < passwordArray.length; i++) {
        if (specialChars.includes(passwordArray[i])) {
          // Replace with a random alphanumeric character
          const alphanumeric = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
          passwordArray[i] = alphanumeric[Math.floor(Math.random() * alphanumeric.length)];
        }
      }
    }

    // Guarantee all required character types are present
    // We'll verify and fix in a loop until all requirements are met
    // This ensures that even if one fix overwrites another requirement, we'll fix it in the next iteration
    let maxIterations = 10; // Prevent infinite loops
    while (maxIterations-- > 0) {
      let allRequirementsMet = true;

      // Check and fix lowercase - replace any character that's not already lowercase
      if (!passwordArray.some(c => lowercase.includes(c))) {
        const index = Math.floor(Math.random() * passwordArray.length);
        passwordArray[index] = lowercase[Math.floor(Math.random() * lowercase.length)];
        allRequirementsMet = false;
      }

      // Check and fix uppercase - replace any character that's not already uppercase
      if (!passwordArray.some(c => uppercase.includes(c))) {
        const index = Math.floor(Math.random() * passwordArray.length);
        passwordArray[index] = uppercase[Math.floor(Math.random() * uppercase.length)];
        allRequirementsMet = false;
      }

      // Check and fix digits - replace any character that's not already a digit
      if (!passwordArray.some(c => digits.includes(c))) {
        const index = Math.floor(Math.random() * passwordArray.length);
        passwordArray[index] = digits[Math.floor(Math.random() * digits.length)];
        allRequirementsMet = false;
      }

      // Check and fix special chars if required - replace any character that's not already a special char
      if (includeSpecialChars && !passwordArray.some(c => specialChars.includes(c))) {
        const index = Math.floor(Math.random() * passwordArray.length);
        passwordArray[index] = specialChars[Math.floor(Math.random() * specialChars.length)];
        allRequirementsMet = false;
      }

      // If all requirements are met, we're done
      if (allRequirementsMet) {
        break;
      }
    }

    return passwordArray.join('');
  }
}
