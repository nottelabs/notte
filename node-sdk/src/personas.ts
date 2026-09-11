import { NotteClient } from '@/client';
import { NotteVault } from '@/vaults';
import type {
  PersonaCreateRequest,
  PersonaResponse,
  EmailResponse,
  SmsResponse,
  PaginatedResponsePersonaResponse,
  PersonaEmailsListData,
  ListPersonasData,
  DeletePersonaResponse
} from '@/lib/client/types.gen';
import {
  personaCreate,
  personaGet,
  personaDelete,
  personaEmailsList,
  personaSmsList,
  listPersonas
} from '@/lib/client/sdk.gen';
import { formatError } from '@/utils';

// Type aliases from generated types for convenience
export type MessageReadOptions = NonNullable<PersonaEmailsListData['query']>;
export type PersonaListOptions = NonNullable<ListPersonasData['query']>;
// Backwards-compatible convenience alias; the generated response now includes
// the internal address directly.
export type PersonaResponseWithInternalEmail = PersonaResponse;

// Constructor overloads for NottePersona - mirrors Python overloads
export interface PersonaConstructorWithId {
  persona_id: string;
}

export interface PersonaConstructorCreate extends PersonaCreateRequest {
  persona_id?: never;
}

export type PersonaConstructor = PersonaConstructorWithId | PersonaConstructorCreate;

/**
 * Self-service identities for web automation (account creation, 2FA, etc.)
 *
 * Notte Personas provide automated identity management for AI agents, enabling them to create accounts,
 * handle two-factor authentication, and interact with web platforms without manual intervention.
 *
 * Notte Personas come with complete digital identities:
 * - Unique Email Address: Dedicated mailbox for each persona with full email management
 * - Phone Number: SMS-capable phone number for verification and 2FA
 * - Credential Vault: Optional secure storage for passwords and authentication tokens
 * - Automated Communication: Built-in email and SMS reading capabilities
 * - 2FA Support: Seamless handling of two-factor authentication flows
 */
export class NottePersona {
  private client: NotteClient;
  private _initRequest: PersonaCreateRequest;
  private response: PersonaResponseWithInternalEmail | null = null;
  private initPromise: Promise<PersonaResponseWithInternalEmail> | null = null;
  private _vault: NotteVault | undefined;
  private readonly ownsPersona: boolean;

  constructor(client: NotteClient, options: PersonaConstructor = {}) {
    this.client = client;
    this.ownsPersona = !('persona_id' in options && options.persona_id);

    if (options && 'persona_id' in options && options.persona_id) {
      // Constructor for existing persona
      this.initPromise = this.initExistingPersona(options.persona_id);
      this._initRequest = {};
    } else {
      // Constructor for new persona - create it
      const createData = (options || {}) as PersonaConstructorCreate;
      this._initRequest = createData;
      this.initPromise = this.initNewPersona(createData);
    }
  }

  /**
   * Get persona info
   */
  get info(): PersonaResponseWithInternalEmail {
    if (this.response === null) {
      throw new Error('Persona not initialized');
    }
    return this.response;
  }

  /**
   * Get vault (cached property equivalent)
   */
  get vault(): NotteVault {
    if (this._vault === undefined) {
      const vault = this._getVault();
      if (vault === null) {
        throw new Error(
          'Persona has no vault. Please create a new persona using `create_vault=true` to use this feature.'
        );
      }
      this._vault = vault;
    }
    return this._vault;
  }

  /**
   * Check if persona has a vault
   */
  get hasVault(): boolean {
    return this.info.vault_id !== null;
  }

  private async initExistingPersona(personaId: string): Promise<PersonaResponseWithInternalEmail> {
    const response = await personaGet({
      client: this.client.getClient(),
      path: {
        persona_id: personaId
      }
    });

    if (response?.error) {
      throw new Error(`Failed to get persona: ${formatError(response.error)}`);
    }

    this.response = response.data as PersonaResponseWithInternalEmail;
    return this.response;
  }

  private async initNewPersona(createData: PersonaCreateRequest): Promise<PersonaResponseWithInternalEmail> {
    const response = await personaCreate({
      client: this.client.getClient(),
      body: createData
    });

    if (response?.error) {
      throw new Error(`Failed to create persona: ${formatError(response.error)}`);
    }

    this.response = response.data as PersonaResponseWithInternalEmail;
    console.warn(
      `[Persona] ${this.response.persona_id} created since no persona id was provided. Please store this to retrieve it later.`
    );
    return this.response;
  }

  private async ensureInitialized(): Promise<PersonaResponseWithInternalEmail> {
    if (this.response) {
      return this.response;
    }
    if (this.initPromise) {
      return await this.initPromise;
    }
    throw new Error('Persona not initialized');
  }

  /**
   * Get persona ID
   */
  get personaId(): string {
    if (!this.response) {
      throw new Error('Persona not initialized. Use await on persona operations first.');
    }
    return this.response.persona_id;
  }

  /**
   * Public, human-readable email address of the persona
   */
  get email(): string {
    return this.info.email;
  }

  /**
   * Internal UUID-backed mailbox address of the persona
   */
  get internalEmail(): string {
    return this.info.internal_email;
  }

  /**
   * Start the persona - ensures initialization
   */
  async start(): Promise<void> {
    await this.ensureInitialized();
  }

  /**
   * Stop the persona - deletes it
   */
  async stop(): Promise<void> {
    await this.ensureInitialized();
    console.log(`[Persona] ${this.personaId} deleted.`);
    await this.delete();
  }

  /**
   * Get vault - private helper method
   */
  private _getVault(): NotteVault | null {
    if (this.info.vault_id === null) {
      return null;
    }
    return new NotteVault(this.client, { vault_id: this.info.vault_id });
  }

  /**
   * Create the persona
   */
  async create(): Promise<void> {
    if (this.response !== null) {
      throw new Error(`Persona ${this.personaId} already initialized`);
    }
    await this.ensureInitialized();
  }

  /**
   * Delete the persona from the notte console
   */
  async delete(): Promise<DeletePersonaResponse> {
    await this.ensureInitialized();
    const response = await personaDelete({
      client: this.client.getClient(),
      path: {
        persona_id: this.personaId
      }
    });

    if (response?.error) {
      throw new Error(`Failed to delete persona: ${formatError(response.error)}`);
    }
    return response.data as DeletePersonaResponse;
  }

  /**
   * Add credentials to the persona (generates a password and stores it in the vault)
   */
  async addCredentials(url: string): Promise<void> {
    const vault = this._getVault();
    if (vault === null) {
      throw new Error(
        'Cannot add credentials to a persona without a vault. Please create a new persona using `create_vault=true` to use this feature.'
      );
    }
    const password = vault.generatePassword();
    await vault.addCredentials(url, {
      email: this.info.email,
      password: password
    });
  }

  /**
   * Read recent emails sent to the persona
   */
  async emails(options?: MessageReadOptions): Promise<EmailResponse[]> {
    await this.ensureInitialized();
    const response = await personaEmailsList({
      client: this.client.getClient(),
      path: {
        persona_id: this.personaId
      },
      query: options || {}
    });

    if (response?.error) {
      throw new Error(`Failed to list emails: ${formatError(response.error)}`);
    }

    return response.data as EmailResponse[];
  }

  /**
   * Read recent SMS messages sent to the persona
   */
  async sms(options?: MessageReadOptions): Promise<SmsResponse[]> {
    await this.ensureInitialized();
    const response = await personaSmsList({
      client: this.client.getClient(),
      path: {
        persona_id: this.personaId
      },
      query: options || {}
    });

    if (response?.error) {
      throw new Error(`Failed to list SMS messages: ${formatError(response.error)}`);
    }

    return response.data as SmsResponse[];
  }

  /**
   * Get persona information (alias for ensureInitialized)
   */
  async get(): Promise<PersonaResponseWithInternalEmail> {
    await this.ensureInitialized();
    return this.response!;
  }

  /**
   * Context manager for automatic cleanup
   */
  async use<T>(callback: (persona: NottePersona) => Promise<T>): Promise<T> {
    await this.ensureInitialized();
    try {
      return await callback(this);
    } finally {
      // Only delete if this persona was created (not loaded from existing ID)
      if (this.ownsPersona) {
        try {
          await this.delete();
        } catch (error) {
          console.warn(`Failed to delete persona during cleanup: ${error}`);
        }
      }
    }
  }
}
