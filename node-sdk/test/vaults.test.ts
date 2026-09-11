import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NotteClient } from '@/client';
import { InvalidRequestError, NotteAPIError } from '@/errors';

const mocks = vi.hoisted(() => ({
  vaultCreate: vi.fn(),
  vaultCredentialsAdd: vi.fn(),
  vaultCredentialsGet: vi.fn(),
  vaultCredentialsDelete: vi.fn(),
  vaultDelete: vi.fn(),
  vaultCredentialsList: vi.fn(),
  vaultCreditCardSet: vi.fn(),
  vaultCreditCardGet: vi.fn(),
  vaultCreditCardDelete: vi.fn(),
}));

vi.mock('@/lib/client/sdk.gen', () => mocks);

import {
  CREDENTIAL_FIELDS,
  NotteVault,
  getRootDomain,
  isValidMfaSecret,
  validateCredentials,
  validateMfaSecret,
  validateUrl,
} from '@/vaults';

const client = {
  getClient: () => ({ id: 'test-client' }),
} as unknown as NotteClient;

function notFound(path = '/vaults/owned-vault-id/credentials'): NotteAPIError {
  return new NotteAPIError(path, 404, { detail: 'No credentials found' });
}

beforeEach(() => {
  Object.values(mocks).forEach(mock => mock.mockReset());
  mocks.vaultCreate.mockResolvedValue({
    data: { vault_id: 'owned-vault-id', name: 'test', created_at: new Date().toISOString() },
  });
  mocks.vaultCredentialsList.mockResolvedValue({ data: { credentials: [] } });
  mocks.vaultCredentialsAdd.mockResolvedValue({ data: { status: 'success' } });
  mocks.vaultCredentialsDelete.mockResolvedValue({ data: { status: 'success' } });
  mocks.vaultDelete.mockResolvedValue({ data: { status: 'success' } });
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  vi.spyOn(console, 'info').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe('getRootDomain / validateUrl (Python validate_url)', () => {
  it.each([
    ['https://www.github.com/login', 'github.com'],
    ['https://test.peeple.com/ok', 'peeple.com'],
    ['peeple.com', 'peeple.com'],
    ['GitHub.COM:443', 'github.com'],
    ['https://shop.example.co.uk/basket', 'example.co.uk'],
    ['https://amazon.com.au', 'amazon.com.au'],
    ['http://localhost:8080/path', 'localhost'],
    ['http://127.0.0.1:8000', '127.0.0.1'],
    ['https://example.com./', 'example.com'],
    ['https://user:pass@mail.example.org/?q=1', 'example.org'], // pragma: allowlist secret
  ])('reduces %s to %s', (url, domain) => {
    expect(getRootDomain(url)).toBe(domain);
    expect(validateUrl(url)).toBe(domain);
  });

  it.each(['', '   ', 'https://', '.com', 'https://.com/'])('rejects %j', url => {
    expect(getRootDomain(url)).toBe('');
    expect(() => validateUrl(url)).toThrow(InvalidRequestError);
    expect(() => validateUrl(url)).toThrow(/valid URL with a domain name/);
  });
});

describe('MFA secret validation (pyotp semantics)', () => {
  it.each(['mysecret', 'short', 'JBSWY3DPEHPK3PXP', 'jbswy3dpehpk3pxp', 'AAAAAAAAAAAA', 'PYNT7I67RFS2EPR5'])(
    'accepts base32 secret %s',
    secret => {
      expect(isValidMfaSecret(secret)).toBe(true);
      expect(() => validateMfaSecret(secret)).not.toThrow();
    },
  );

  it.each(['999777', '', 'ABC=', 'a b', 'secret!', '1234567890'])('rejects %j', secret => {
    expect(isValidMfaSecret(secret)).toBe(false);
    expect(() => validateMfaSecret(secret)).toThrow(InvalidRequestError);
    expect(() => validateMfaSecret(secret)).toThrow(/did you try to store an OTP instead of a secret/);
  });
});

describe('validateCredentials (AddCredentialsRequest rules)', () => {
  it('requires exactly one of username or email', () => {
    expect(() => validateCredentials({ password: 'x' })).toThrow('Need to have either username or email set');
    expect(() => validateCredentials({ password: 'x', email: 'a@b.c', username: 'a' })).toThrow(
      'Can only set either username or email',
    );
    expect(validateCredentials({ password: 'x', email: 'a@b.c' })).toEqual({ password: 'x', email: 'a@b.c' });
    expect(validateCredentials({ password: 'x', username: 'a' })).toEqual({ password: 'x', username: 'a' });
  });

  it('validates the MFA secret when present', () => {
    expect(() => validateCredentials({ password: 'x', email: 'a@b.c', mfa_secret: '999777' })).toThrow(InvalidRequestError);
    expect(() => validateCredentials({ password: 'x', email: 'a@b.c', mfa_secret: 'mysecret' })).not.toThrow();
  });
});

describe('NotteVault initialization', () => {
  it('does not create a remote vault when using a local-only password helper', () => {
    const vault = new NotteVault(client);

    expect(vault.generatePassword()).toBeTypeOf('string');
    expect(mocks.vaultCreate).not.toHaveBeenCalled();
    expect(() => vault.vaultId).toThrow(InvalidRequestError);
  });

  it('creates the remote vault once when an API operation needs it', async () => {
    const vault = new NotteVault(client, { name: 'My vault' });

    await vault.listCredentials();
    await vault.listCredentials();

    expect(mocks.vaultCreate).toHaveBeenCalledTimes(1);
    expect(mocks.vaultCreate.mock.calls[0]![0].body).toEqual({ name: 'My vault' });
    expect(vault.vaultId).toBe('owned-vault-id');
  });

  it('verifies an existing vault by listing its credentials', async () => {
    const vault = new NotteVault(client, { vault_id: 'existing-vault' });
    await vault.listCredentials();

    expect(mocks.vaultCreate).not.toHaveBeenCalled();
    expect(mocks.vaultCredentialsList.mock.calls[0]![0].path).toEqual({ vault_id: 'existing-vault' });
    expect(vault.vaultId).toBe('existing-vault');
  });

  it('surfaces a missing existing vault as the API error', async () => {
    mocks.vaultCredentialsList.mockRejectedValue(new NotteAPIError('/vaults/missing/credentials', 404, { detail: 'not found' }));
    const vault = new NotteVault(client, { vault_id: 'missing' });
    await expect(vault.listCredentials()).rejects.toBeInstanceOf(NotteAPIError);
  });

  it('rejects an empty vault id synchronously', () => {
    expect(() => new NotteVault(client, { vault_id: '' })).toThrow(InvalidRequestError);
  });

  it('no longer exposes credit card operations', () => {
    const vault = new NotteVault(client) as unknown as Record<string, unknown>;
    expect(vault.setCreditCard).toBeUndefined();
    expect(vault.getCreditCard).toBeUndefined();
    expect(vault.deleteCreditCard).toBeUndefined();
  });
});

describe('NotteVault credentials', () => {
  it('adds credentials with the root domain as URL', async () => {
    const vault = new NotteVault(client);
    await vault.addCredentials('https://github.com/login', { email: 'me@example.org', password: 'pw' }); // pragma: allowlist secret

    expect(mocks.vaultCredentialsAdd).toHaveBeenCalledWith(
      expect.objectContaining({
        path: { vault_id: 'owned-vault-id' },
        body: { url: 'github.com', credentials: { email: 'me@example.org', password: 'pw' } }, // pragma: allowlist secret
      }),
    );
  });

  it.each([
    ['an invalid URL', 'https://', { email: 'me@example.org', password: 'pw' }], // pragma: allowlist secret
    ['a one-time code as MFA secret', 'https://github.com/', { email: 'me@example.org', password: 'pw', mfa_secret: '999777' }], // pragma: allowlist secret
    ['both username and email', 'https://github.com/', { email: 'me@example.org', username: 'me', password: 'pw' }], // pragma: allowlist secret
    ['neither username nor email', 'https://github.com/', { password: 'pw' }], // pragma: allowlist secret
  ])('rejects %s before touching the API', async (_label, url, credentials) => {
    const vault = new NotteVault(client);
    await expect(vault.addCredentials(url, credentials)).rejects.toBeInstanceOf(InvalidRequestError);
    expect(mocks.vaultCreate).not.toHaveBeenCalled();
    expect(mocks.vaultCredentialsAdd).not.toHaveBeenCalled();
  });

  it('returns credentials and queries by root domain', async () => {
    mocks.vaultCredentialsGet.mockResolvedValue({ data: { credentials: { email: 'me@example.org', password: 'pw' } } }); // pragma: allowlist secret
    const vault = new NotteVault(client, { vault_id: 'existing-vault' });

    await expect(vault.getCredentials('https://github.com/login')).resolves.toEqual({
      email: 'me@example.org',
      password: 'pw', // pragma: allowlist secret
    });
    expect(mocks.vaultCredentialsGet).toHaveBeenCalledWith(
      expect.objectContaining({ path: { vault_id: 'existing-vault' }, query: { url: 'github.com' } }),
    );
  });

  it('propagates API errors from getCredentials instead of returning null', async () => {
    mocks.vaultCredentialsGet.mockRejectedValue(notFound());
    const vault = new NotteVault(client);

    const failure = vault.getCredentials('https://nonexistent.com/');
    await expect(failure).rejects.toBeInstanceOf(NotteAPIError);
    await expect(failure).rejects.toMatchObject({ statusCode: 404 });
  });

  it('deletes credentials by root domain', async () => {
    const vault = new NotteVault(client);
    await vault.deleteCredentials('https://www.gmail.com/');
    expect(mocks.vaultCredentialsDelete).toHaveBeenCalledWith(
      expect.objectContaining({ path: { vault_id: 'owned-vault-id' }, query: { url: 'gmail.com' } }),
    );
  });

  it('propagates API errors from deleteCredentials and listCredentials', async () => {
    mocks.vaultCredentialsDelete.mockRejectedValue(notFound());
    const vault = new NotteVault(client);
    await expect(vault.deleteCredentials('https://gmail.com/')).rejects.toBeInstanceOf(NotteAPIError);

    mocks.vaultCredentialsList.mockRejectedValue(new NotteAPIError('/vaults/x/credentials', 500, { message: 'boom' }));
    await expect(vault.listCredentials()).rejects.toMatchObject({ statusCode: 500 });
  });

  it('lists credentials', async () => {
    mocks.vaultCredentialsList.mockResolvedValue({
      data: { credentials: [{ url: 'github.com', email: 'me@example.org', username: null }] },
    });
    const vault = new NotteVault(client);
    await expect(vault.listCredentials()).resolves.toEqual([{ url: 'github.com', email: 'me@example.org', username: null }]);
  });

  it('hasCredential checks the listing, accepting full URLs and stored domains', async () => {
    mocks.vaultCredentialsList.mockResolvedValue({
      data: { credentials: [{ url: 'github.com', email: 'me@example.org', username: null }] },
    });
    const vault = new NotteVault(client);

    await expect(vault.hasCredential('https://github.com/login')).resolves.toBe(true);
    await expect(vault.hasCredential('github.com')).resolves.toBe(true);
    await expect(vault.hasCredential('https://gitlab.com/')).resolves.toBe(false);
    await expect(vault.hasCredential('not a url')).resolves.toBe(false);
    expect(mocks.vaultCredentialsGet).not.toHaveBeenCalled();
  });

  it('hasCredential propagates API errors', async () => {
    mocks.vaultCredentialsList.mockRejectedValue(new NotteAPIError('/vaults/x/credentials', 500, { message: 'boom' }));
    const vault = new NotteVault(client, { vault_id: 'existing-vault' });
    await expect(vault.hasCredential('https://github.com/')).rejects.toBeInstanceOf(NotteAPIError);
  });
});

describe('NotteVault addCredentialsFromEnv', () => {
  it('reads {DOMAIN}_* variables for the root domain', async () => {
    vi.stubEnv('PEEPLE_COM_EMAIL', 'xyz@notte.cc');
    vi.stubEnv('PEEPLE_COM_PASSWORD', 'xyz');
    vi.stubEnv('PEEPLE_COM_MFA_SECRET', 'JBSWY3DPEHPK3PXP');
    const vault = new NotteVault(client);

    await vault.addCredentialsFromEnv('https://test.peeple.com/ok');

    expect(mocks.vaultCredentialsAdd).toHaveBeenCalledWith(
      expect.objectContaining({
        body: {
          url: 'peeple.com',
          credentials: { email: 'xyz@notte.cc', password: 'xyz', mfa_secret: 'JBSWY3DPEHPK3PXP' },
        },
      }),
    );
  });

  it('supports username based credentials', async () => {
    vi.stubEnv('TEST_COM_USERNAME', 'my_xyz_username');
    vi.stubEnv('TEST_COM_PASSWORD', 'my_xyz_password');
    const vault = new NotteVault(client);

    await vault.addCredentialsFromEnv('https://test.com');

    expect(mocks.vaultCredentialsAdd.mock.calls[0]![0].body).toEqual({
      url: 'test.com',
      credentials: { username: 'my_xyz_username', password: 'my_xyz_password' }, // pragma: allowlist secret
    });
  });

  it('lists the expected variables when none are set', async () => {
    const vault = new NotteVault(client);
    const failure = vault.addCredentialsFromEnv('https://example.com/');
    await expect(failure).rejects.toBeInstanceOf(InvalidRequestError);
    await expect(failure).rejects.toThrow(
      `No credentials found in the environment for https://example.com/. Please set the following variables: ${CREDENTIAL_FIELDS.map(field => `EXAMPLE_COM_${field.toUpperCase()}`).join(', ')}`,
    );
    expect(mocks.vaultCreate).not.toHaveBeenCalled();
  });

  it('rejects an invalid MFA secret read from the environment', async () => {
    vi.stubEnv('EXAMPLE_COM_EMAIL', 'me@example.org');
    vi.stubEnv('EXAMPLE_COM_PASSWORD', 'pw');
    vi.stubEnv('EXAMPLE_COM_MFA_SECRET', '999777');
    const vault = new NotteVault(client);
    await expect(vault.addCredentialsFromEnv('https://example.com/')).rejects.toBeInstanceOf(InvalidRequestError);
    expect(mocks.vaultCredentialsAdd).not.toHaveBeenCalled();
  });
});

describe('NotteVault lifecycle', () => {
  it('stop() deletes the vault', async () => {
    const vault = new NotteVault(client);
    await vault.listCredentials();
    await vault.stop();
    expect(mocks.vaultDelete).toHaveBeenCalledWith(expect.objectContaining({ path: { vault_id: 'owned-vault-id' } }));
  });

  it('delete() propagates API errors', async () => {
    mocks.vaultDelete.mockRejectedValue(new NotteAPIError('/vaults/owned-vault-id', 500, { message: 'boom' }));
    const vault = new NotteVault(client);
    await expect(vault.delete()).rejects.toBeInstanceOf(NotteAPIError);
  });

  it('start() is a no-op', () => {
    const vault = new NotteVault(client);
    expect(vault.start()).toBeUndefined();
    expect(mocks.vaultCreate).not.toHaveBeenCalled();
  });
});

describe('NotteVault generatePassword', () => {
  const SPECIAL = /[!@#$%^&*()_+\-=[\]|;:,.<>?]/;

  it('meets every character class requirement', () => {
    const vault = new NotteVault(client);
    for (let i = 0; i < 50; i += 1) {
      const password = vault.generatePassword();
      expect(password).toHaveLength(20);
      expect(password).toMatch(/[a-z]/);
      expect(password).toMatch(/[A-Z]/);
      expect(password).toMatch(/[0-9]/);
      expect(password).toMatch(SPECIAL);
    }
  });

  it('omits special characters on request', () => {
    const vault = new NotteVault(client);
    for (let i = 0; i < 50; i += 1) {
      const password = vault.generatePassword(15, false);
      expect(password).toHaveLength(15);
      expect(password).toMatch(/[a-z]/);
      expect(password).toMatch(/[A-Z]/);
      expect(password).toMatch(/[0-9]/);
      expect(password).not.toMatch(SPECIAL);
    }
  });

  it('rejects lengths that cannot satisfy the requirements', () => {
    const vault = new NotteVault(client);
    expect(() => vault.generatePassword(2)).toThrow(InvalidRequestError);
    expect(() => vault.generatePassword(2)).toThrow('Password length must be at least 4 characters');
    expect(() => vault.generatePassword(2, false)).toThrow('Password length must be at least 3 characters');
  });

  it('is random', () => {
    const vault = new NotteVault(client);
    expect(vault.generatePassword()).not.toBe(vault.generatePassword());
  });
});
