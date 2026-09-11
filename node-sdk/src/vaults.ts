import type { NotteClient } from '@/client';
import type {
  Credential,
  CredentialsDictInput,
  CredentialsDictOutput,
  Vault,
  VaultCreateRequest,
} from '@/lib/client/types.gen';
import {
  vaultCreate,
  vaultCredentialsAdd,
  vaultCredentialsDelete,
  vaultCredentialsGet,
  vaultCredentialsList,
  vaultDelete,
} from '@/lib/client/sdk.gen';
import { InvalidRequestError } from '@/errors';

// Constructor overloads for NotteVault - mirrors Python overloads
export interface VaultConstructorWithId {
  vault_id: string;
}

export interface VaultConstructorCreate extends VaultCreateRequest {
  vault_id?: never;
}

export type VaultConstructor = VaultConstructorWithId | VaultConstructorCreate;

/** Credential fields read by `addCredentialsFromEnv`, in the order Python's `CredentialField.registry` declares them. */
export const CREDENTIAL_FIELDS = ['email', 'username', 'mfa_secret', 'password'] as const;
export type CredentialField = (typeof CREDENTIAL_FIELDS)[number];

/**
 * Second-level labels that form a public suffix together with a two-letter
 * country code (`example.co.uk`, `shop.com.au`). Python resolves this with the
 * full public suffix list through `tldextract`; this SDK ships a compact rule
 * instead so no dependency is needed.
 */
const COUNTRY_SECOND_LEVEL_LABELS = new Set([
  'ac', 'co', 'com', 'edu', 'gov', 'ltd', 'me', 'mil', 'ne', 'net', 'nom', 'or', 'org', 'plc', 'sch',
]);

function extractHostname(url: string): string {
  const trimmed = url.trim();
  if (trimmed.length === 0) {
    return '';
  }
  // Bare domains (`peeple.com`, `github.com:443`) get a scheme so `URL` can parse them.
  const hasScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed);
  const candidates = hasScheme ? [trimmed] : [`https://${trimmed}`];
  for (const candidate of candidates) {
    try {
      const { hostname } = new URL(candidate);
      // Python's tldextract yields an empty domain for names starting with a dot.
      if (hostname.length > 0 && !hostname.startsWith('.')) {
        return hostname.toLowerCase();
      }
    } catch {
      // Not parseable: no domain.
    }
  }
  return '';
}

/**
 * Get the root domain of a URL, the counterpart of `notte_core.utils.url.get_root_domain`.
 * Returns an empty string when no domain can be extracted.
 *
 * ```ts
 * getRootDomain('https://www.example.com/path'); // 'example.com'
 * getRootDomain('https://test.peeple.com/ok'); // 'peeple.com'
 * getRootDomain('https://shop.example.co.uk'); // 'example.co.uk'
 * ```
 */
export function getRootDomain(url: string): string {
  const hostname = extractHostname(url);
  if (hostname.length === 0) {
    return '';
  }
  // IPv6 literals and IPv4 addresses have no public suffix: keep them whole.
  if (hostname.startsWith('[') || /^\d{1,3}(\.\d{1,3}){3}$/.test(hostname)) {
    return hostname;
  }
  const labels = hostname.split('.').filter(label => label.length > 0);
  if (labels.length === 0) {
    return '';
  }
  if (labels.length <= 2) {
    return labels.join('.');
  }
  const tld = labels[labels.length - 1]!;
  const secondLevel = labels[labels.length - 2]!;
  const suffixLength = tld.length === 2 && COUNTRY_SECOND_LEVEL_LABELS.has(secondLevel) ? 2 : 1;
  return labels.slice(-(suffixLength + 1)).join('.');
}

/**
 * Normalise a credential URL to its root domain, the counterpart of
 * `notte_sdk.types.validate_url`. Throws `InvalidRequestError` when the URL
 * has no domain name.
 *
 * ```ts
 * validateUrl('https://github.com/login'); // 'github.com'
 * validateUrl('https://'); // throws InvalidRequestError
 * ```
 */
export function validateUrl(url: string): string {
  const domain = getRootDomain(url);
  if (domain.length === 0) {
    throw new InvalidRequestError(`Invalid URL: ${url}. Please provide a valid URL with a domain name.`);
  }
  return domain;
}

/**
 * Check that a string is a base32 TOTP secret, with the padding rules Python's
 * `pyotp.TOTP(secret).now()` applies (`base64.b32decode` after right-padding
 * the secret to a multiple of eight characters).
 */
export function isValidMfaSecret(secret: string): boolean {
  if (secret.length === 0) {
    return false;
  }
  let padded = secret.toUpperCase();
  if (padded.length % 8 !== 0) {
    padded += '='.repeat(8 - (padded.length % 8));
  }
  let end = padded.length;
  while (end > 0 && padded[end - 1] === '=') {
    end -= 1;
  }
  const stripped = padded.slice(0, end);
  const padding = padded.length - stripped.length;
  return /^[A-Z2-7]*$/.test(stripped) && [0, 1, 3, 4, 6].includes(padding);
}

/**
 * Validate an MFA secret like `AddCredentialsRequest.check_email_and_username`
 * in Python. Rejects one-time codes (`999777`) and anything that is not base32.
 */
export function validateMfaSecret(secret: string): void {
  if (!isValidMfaSecret(secret)) {
    throw new InvalidRequestError('Invalid MFA secret code: did you try to store an OTP instead of a secret?');
  }
}

/**
 * Apply the client-side rules of Python's `AddCredentialsRequest`: exactly one
 * of `username` / `email`, and a base32 `mfa_secret` when one is provided.
 * Returns the credentials unchanged.
 */
export function validateCredentials(credentials: CredentialsDictInput): CredentialsDictInput {
  const hasUsername = credentials.username !== undefined && credentials.username !== null;
  const hasEmail = credentials.email !== undefined && credentials.email !== null;
  if (hasUsername && hasEmail) {
    throw new InvalidRequestError('Can only set either username or email');
  }
  if (!hasUsername && !hasEmail) {
    throw new InvalidRequestError('Need to have either username or email set');
  }
  if (credentials.mfa_secret !== undefined && credentials.mfa_secret !== null) {
    validateMfaSecret(credentials.mfa_secret);
  }
  return credentials;
}

/**
 * Vault that fetches credentials stored using the SDK, the counterpart of
 * `notte_sdk.endpoints.vaults.NotteVault`.
 *
 * The remote vault is created lazily on the first API operation so local-only
 * helpers such as `generatePassword()` stay side-effect free. Every API
 * failure rejects with a `NotteAPIError`; caller mistakes (invalid URL,
 * one-time code stored as an MFA secret, ...) reject with `InvalidRequestError`.
 * // pragma: allowlist secret
 * ```ts
 * const vault = client.Vault({ name: 'My vault' });
 * await vault.addCredentials('https://github.com/', { email: 'me@example.org', password: 'secret' }); // pragma: allowlist secret
 * const credentials = await vault.getCredentials('https://github.com/login');
 * await vault.stop(); // deletes the vault and every credential it holds
 * ```
 */
export class NotteVault {
  private client: NotteClient;
  private _vaultId: string | null = null;
  private initPromise: Promise<string> | null = null;
  private createData: VaultCreateRequest | null = null;

  constructor(client: NotteClient, options: VaultConstructor = {}) {
    this.client = client;

    if (options && 'vault_id' in options && options.vault_id !== undefined) {
      // Constructor for existing vault
      if (options.vault_id.length === 0) {
        throw new InvalidRequestError('Vault ID cannot be empty');
      }
      this.initPromise = this.initExistingVault(options.vault_id);
      // The rejection is surfaced by the first awaited operation; avoid an
      // unhandled rejection when verification fails before anything is awaited.
      this.initPromise.catch(() => undefined);
    } else {
      // Defer remote creation until an operation actually needs a vault. This
      // keeps local-only helpers such as generatePassword() side-effect free.
      const { vault_id: _ignored, ...createData } = (options ?? {}) as VaultConstructorCreate;
      this.createData = createData;
    }
  }

  private async initExistingVault(vaultId: string): Promise<string> {
    await this.verifyVaultExists(vaultId);
    this._vaultId = vaultId;
    return this._vaultId;
  }

  private async initNewVault(createData: VaultCreateRequest): Promise<string> {
    const response = await vaultCreate({
      client: this.client.getClient(),
      body: createData,
      throwOnError: true,
    });
    const vault: Vault = response.data;
    console.warn(`[Vault] ${vault.vault_id} created since no vault id was provided. Please store this to retrieve it later.`);
    this._vaultId = vault.vault_id;
    return this._vaultId;
  }

  private async verifyVaultExists(vaultId: string): Promise<void> {
    // Verify the vault exists by listing its credentials; a missing vault rejects with a NotteAPIError.
    await vaultCredentialsList({
      client: this.client.getClient(),
      path: { vault_id: vaultId },
      throwOnError: true,
    });
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
    throw new InvalidRequestError('Vault not initialized');
  }

  /** ID of the remote vault. Throws until the first API operation has created or verified it. */
  get vaultId(): string {
    if (!this._vaultId) {
      throw new InvalidRequestError('Vault not initialized. Await a vault operation first.');
    }
    return this._vaultId;
  }

  /**
   * Start the vault. No-op kept for parity with Python's `SyncResource` interface.
   */
  start(): void {
    // No-op - vault is ready to use immediately
  }

  /**
   * Stop the vault: deletes it together with every credential it holds.
   *
   * ```ts
   * await vault.stop();
   * ```
   */
  async stop(): Promise<void> {
    const vaultId = await this.ensureInitialized();
    console.info(`[Vault] ${vaultId} deleted. All credentials have been deleted.`);
    await this.delete();
  }

  /**
   * Add or update the credentials stored for a website. The URL is reduced to
   * its root domain (`https://github.com/login` → `github.com`) before it is
   * sent, like Python's `AddCredentialsRequest`.
   *
   * ```ts
   * await vault.addCredentials('https://github.com/', {
   *   email: 'me@example.org',
   *   password: 'secret', // pragma: allowlist secret
   *   mfa_secret: 'JBSWY3DPEHPK3PXP', // pragma: allowlist secret
   * });
   * ```
   */
  async addCredentials(url: string, credentials: CredentialsDictInput): Promise<void> {
    const domain = validateUrl(url);
    validateCredentials(credentials);
    const vaultId = await this.ensureInitialized();
    await vaultCredentialsAdd({
      client: this.client.getClient(),
      path: { vault_id: vaultId },
      body: { url: domain, credentials },
      throwOnError: true,
    });
  }

  /**
   * Get the credentials stored for a website. Rejects with a `NotteAPIError`
   * when the vault holds no credentials for that domain, like Python's
   * `get_credentials`.
   *
   * ```ts
   * const { email, password } = await vault.getCredentials('https://github.com/login');
   * ```
   */
  async getCredentials(url: string): Promise<CredentialsDictOutput> {
    const domain = validateUrl(url);
    const vaultId = await this.ensureInitialized();
    const response = await vaultCredentialsGet({
      client: this.client.getClient(),
      path: { vault_id: vaultId },
      query: { url: domain },
      throwOnError: true,
    });
    return response.data.credentials;
  }

  /**
   * Check whether the vault holds credentials for a website, the counterpart
   * of `BaseVault.has_credential`. Never rejects for a missing credential.
   *
   * ```ts
   * if (!(await vault.hasCredential('https://github.com/'))) {
   *   await vault.addCredentialsFromEnv('https://github.com/');
   * }
   * ```
   */
  async hasCredential(url: string): Promise<boolean> {
    const domain = getRootDomain(url);
    const credentials = await this.listCredentials();
    return credentials.some(credential => credential.url === url || credential.url === domain);
  }

  /**
   * Delete the credentials stored for a website.
   *
   * ```ts
   * await vault.deleteCredentials('https://github.com/');
   * ```
   */
  async deleteCredentials(url: string): Promise<void> {
    const domain = validateUrl(url);
    const vaultId = await this.ensureInitialized();
    await vaultCredentialsDelete({
      client: this.client.getClient(),
      path: { vault_id: vaultId },
      query: { url: domain },
      throwOnError: true,
    });
  }

  /**
   * List the websites the vault holds credentials for. Passwords are never returned.
   *
   * ```ts
   * const credentials = await vault.listCredentials();
   * console.log(credentials.map(c => c.url));
   * ```
   */
  async listCredentials(): Promise<Credential[]> {
    const vaultId = await this.ensureInitialized();
    const response = await vaultCredentialsList({
      client: this.client.getClient(),
      path: { vault_id: vaultId },
      throwOnError: true,
    });
    return response.data.credentials;
  }

  /**
   * Delete the vault and every credential it holds.
   */
  async delete(): Promise<void> {
    const vaultId = await this.ensureInitialized();
    await vaultDelete({
      client: this.client.getClient(),
      path: { vault_id: vaultId },
      throwOnError: true,
    });
  }

  /**
   * Add credentials read from environment variables, the counterpart of
   * `BaseVault.add_credentials_from_env`. For `https://github.com/` the
   * variables are `GITHUB_COM_EMAIL`, `GITHUB_COM_USERNAME`,
   * `GITHUB_COM_MFA_SECRET` and `GITHUB_COM_PASSWORD`.
   *
   * ```ts
   * process.env.GITHUB_COM_EMAIL = 'me@example.org';
   * process.env.GITHUB_COM_PASSWORD = 'secret'; // pragma: allowlist secret
   * await vault.addCredentialsFromEnv('https://github.com/');
   * ```
   */
  async addCredentialsFromEnv(url: string): Promise<void> {
    const rootDomain = validateUrl(url);
    const prefix = rootDomain.replace(/\./g, '_').toUpperCase();
    const credentials: Partial<CredentialsDictInput> = {};
    const variableNames: string[] = [];
    for (const field of CREDENTIAL_FIELDS) {
      const variable = `${prefix}_${field.toUpperCase()}`;
      variableNames.push(variable);
      const value = process.env[variable];
      if (value !== undefined) {
        credentials[field] = value;
      }
    }
    if (Object.keys(credentials).length === 0) {
      throw new InvalidRequestError(
        `No credentials found in the environment for ${url}. Please set the following variables: ${variableNames.join(', ')}`,
      );
    }
    await this.addCredentials(url, credentials as CredentialsDictInput);
  }

  /**
   * Generate a secure random password, the counterpart of Python's
   * `generate_password`. The result always contains a lowercase letter, an
   * uppercase letter and a digit, plus a special character unless
   * `includeSpecialChars` is false.
   *
   * ```ts
   * const password = vault.generatePassword(24);
   * ```
   */
  generatePassword(length: number = 20, includeSpecialChars: boolean = true): string {
    // Validate minimum length
    const minRequiredLength = includeSpecialChars ? 4 : 3;
    if (length < minRequiredLength) {
      throw new InvalidRequestError(`Password length must be at least ${minRequiredLength} characters`);
    }

    // Character sets
    const lowercase = 'abcdefghijklmnopqrstuvwxyz';
    const uppercase = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    const digits = '0123456789';
    const specialChars = '!@#$%^&*()_+-=[]|;:,.<>?';
    const alphanumeric = uppercase + lowercase + digits;

    // Generate the initial random password from the platform CSPRNG.
    const allowedChars = includeSpecialChars ? `${alphanumeric}-_` : alphanumeric;
    // Rejection sampling keeps the CSPRNG output uniform: a plain modulo would
    // favour the first `2^32 mod size` characters.
    const randomIndex = (size: number): number => {
      const limit = Math.floor(0x1_0000_0000 / size) * size;
      const buffer = new Uint32Array(1);
      for (;;) {
        const [value] = globalThis.crypto.getRandomValues(buffer);
        if (value! < limit) {
          return value! % size;
        }
      }
    };
    const passwordArray = Array.from({ length }, () => allowedChars[randomIndex(allowedChars.length)]!);
    const pick = (chars: string): string => chars[randomIndex(chars.length)]!;

    // Guarantee every required character class is present. Fixing one class
    // may overwrite another, so loop until all requirements hold.
    let maxIterations = 10;
    while (maxIterations-- > 0) {
      let allRequirementsMet = true;
      const requirements: Array<[boolean, string]> = [
        [true, lowercase],
        [true, uppercase],
        [true, digits],
        [includeSpecialChars, specialChars],
      ];
      for (const [required, chars] of requirements) {
        if (required && !passwordArray.some(c => chars.includes(c))) {
          passwordArray[randomIndex(passwordArray.length)] = pick(chars);
          allRequirementsMet = false;
        }
      }
      if (allRequirementsMet) {
        break;
      }
    }

    return passwordArray.join('');
  }
}
