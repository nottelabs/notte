import { describe, it, expect } from 'vitest';
import { Encryption } from '@/encryption';

// Fixture generated with the python SDK, so that a drift in either
// implementation fails here:
//
//   from notte_core.utils.encryption import Encryption
//   Encryption(root_key=ROOT_KEY).encrypt(PLAINTEXT)
const ROOT_KEY = 'public-sdk-test-key'; // pragma: allowlist secret
const PLAINTEXT = 'https://example.com/function.py?signature=test';
const TOKEN =
	'qWKF5mcl2_w6hv6qHgdIi2dBQUFBQUJxbzlpRElXZlhzUHYzNEV3SGVqSDQ1MjRVMkNUcGx6Z3ZnMDlLdmhMWEx6YXY5Sk0zTzZIMWgxT0tUYmhfM0JRWW9RbE1uYUlOOEhRc0FiTXBvWXRraTZkUmd6WHR1eXcwbERnR3o0UDI3X2xlSWRFa1l5bUtsSW4yOGdrdkk0dE9BZXRU'; // pragma: allowlist secret

describe('Encryption', () => {
	it('should decrypt a token produced by the python SDK', () => {
		expect(new Encryption(ROOT_KEY).decrypt(TOKEN)).toBe(PLAINTEXT);
	});

	it('should reject an empty root key', () => {
		expect(() => new Encryption('')).toThrow('Root key cannot be empty');
	});

	it('should throw when the root key is wrong', () => {
		expect(() => new Encryption('not-the-right-key').decrypt(TOKEN)).toThrow(
			'signature verification failed'
		);
	});

	it('should throw when the token is tampered with', () => {
		const tampered = Buffer.from(TOKEN, 'base64url');
		// Flip a bit in the salt, so the derived key no longer matches the signature.
		tampered[0] ^= 0xff;
		expect(() => new Encryption(ROOT_KEY).decrypt(tampered.toString('base64url'))).toThrow(
			'signature verification failed'
		);
	});

	it('should throw when the token is too short to hold a salt', () => {
		expect(() => new Encryption(ROOT_KEY).decrypt(Buffer.alloc(8).toString('base64url'))).toThrow(
			'too short to contain a salt'
		);
	});
});
