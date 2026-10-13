import { createDecipheriv, createHmac, pbkdf2Sync, timingSafeEqual } from 'node:crypto';

const SALT_LENGTH = 16;
const PBKDF2_ITERATIONS = 100000;
const PBKDF2_KEY_LENGTH = 32;

const FERNET_VERSION = 0x80;
const FERNET_IV_LENGTH = 16;
const FERNET_HMAC_LENGTH = 32;
// version byte + 8 byte timestamp + IV
const FERNET_HEADER_LENGTH = 1 + 8 + FERNET_IV_LENGTH;

/**
 * Decrypts the tokens produced by `notte_core.utils.encryption.Encryption`.
 *
 * A token is `base64url(salt || fernet_token)`. The Fernet key is derived from
 * the root key with PBKDF2-HMAC-SHA256 (100k iterations) over that salt, and the
 * Fernet token itself is AES-128-CBC with an HMAC-SHA256 suffix.
 */
export class Encryption {
	private readonly rootKey: string;

	constructor(rootKey: string) {
		if (!rootKey) {
			throw new Error('Root key cannot be empty');
		}
		this.rootKey = rootKey;
	}

	decrypt(token: string): string {
		const combined = Buffer.from(token, 'base64url');
		if (combined.length <= SALT_LENGTH) {
			throw new Error('Invalid encrypted token: too short to contain a salt');
		}

		const salt = combined.subarray(0, SALT_LENGTH);
		const fernetToken = combined.subarray(SALT_LENGTH).toString('utf8');
		const key = pbkdf2Sync(this.rootKey, salt, PBKDF2_ITERATIONS, PBKDF2_KEY_LENGTH, 'sha256');

		return decryptFernet(fernetToken, key);
	}
}

function decryptFernet(token: string, key: Buffer): string {
	const signingKey = key.subarray(0, 16);
	const encryptionKey = key.subarray(16);

	const data = Buffer.from(token, 'base64url');
	if (data.length < FERNET_HEADER_LENGTH + FERNET_HMAC_LENGTH) {
		throw new Error('Invalid Fernet token: too short');
	}
	if (data[0] !== FERNET_VERSION) {
		throw new Error(`Invalid Fernet token: unsupported version 0x${data[0].toString(16)}`);
	}

	const signed = data.subarray(0, data.length - FERNET_HMAC_LENGTH);
	const signature = data.subarray(data.length - FERNET_HMAC_LENGTH);
	const expected = createHmac('sha256', signingKey).update(signed).digest();
	if (!timingSafeEqual(signature, expected)) {
		throw new Error('Invalid Fernet token: signature verification failed');
	}

	const iv = signed.subarray(9, FERNET_HEADER_LENGTH);
	const ciphertext = signed.subarray(FERNET_HEADER_LENGTH);
	const decipher = createDecipheriv('aes-128-cbc', encryptionKey, iv);

	return Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString('utf8');
}
