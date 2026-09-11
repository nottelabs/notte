import { createWriteStream } from 'node:fs';
import { mkdir, readFile, rename, rm, stat } from 'node:fs/promises';
import { basename, extname, join } from 'node:path';
import { randomBytes } from 'node:crypto';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import type { ReadableStream as NodeReadableStream } from 'node:stream/web';

import type { NotteClient } from '@/client';
import type { Client } from '@/lib/client/client/types.gen';
import type { FileSource, SessionFile, SessionFilesPage } from '@/lib/client/types.gen';
import { deleteSessionFile, downloadSessionFile, listSessionFiles, uploadSessionFile } from '@/lib/client/sdk.gen';
import { InvalidRequestError, NotteError } from '@/errors';

export type { FileSource, SessionFile, SessionFilesPage };

/** A file ID was not found in the session, the counterpart of Python's `FileNotFoundError`. */
export class FileNotFoundError extends NotteError {}

/** The download destination already exists, the counterpart of Python's `FileExistsError`. */
export class FileExistsError extends NotteError {}

export interface FileListOptions {
  /** Only return files from this source: `user_upload` or `session_download`. */
  source?: FileSource;
  /** Page size. Defaults to 100. */
  limit?: number;
  /** Page offset. Defaults to 0. */
  offset?: number;
}

export interface FileDownloadOptions {
  /** Overwrite an existing local file instead of rejecting with `FileExistsError`. */
  force?: boolean;
}

/** Bytes accepted by `upload()`: a local path, a `Blob`/`File`, or an in-memory buffer. */
export type UploadableFile = string | Blob | Uint8Array;

/** Page size used when scanning a session for a file ID, like Python's `metadata()`. */
const METADATA_PAGE_SIZE = 1000;

const MIME_TYPES_BY_EXTENSION: Record<string, string> = {
  '.csv': 'text/csv',
  '.gif': 'image/gif',
  '.htm': 'text/html',
  '.html': 'text/html',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.json': 'application/json',
  '.md': 'text/markdown',
  '.pdf': 'application/pdf',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.txt': 'text/plain',
  '.webp': 'image/webp',
  '.xml': 'application/xml',
  '.zip': 'application/zip',
};

function guessMimeType(filename: string): string {
  return MIME_TYPES_BY_EXTENSION[extname(filename).toLowerCase()] ?? 'application/octet-stream';
}

/**
 * Reduce a server-provided filename to a safe basename, like Python's
 * `Path(PureWindowsPath(filename).name).name`: both separators are honoured,
 * drive letters are dropped and only the last component is kept.
 */
export function sanitizeFilename(filename: string): string {
  const segment = filename.split(/[\\/]+/).filter(Boolean).pop() ?? '';
  return segment.replace(/^[a-zA-Z]:/, '');
}

function toFile(file: Blob | Uint8Array, filename: string): File {
  if (file instanceof File && file.name === filename) {
    return file;
  }
  const type = file instanceof Blob && file.type ? file.type : guessMimeType(filename);
  return new File([file as BlobPart], filename, { type });
}

/**
 * Session-scoped file operations built on the generated `sessions/{id}/files`
 * client. Every API failure rejects with a `NotteAPIError`.
 *
 * ```ts
 * const files = client.Files(sessionId);
 * const uploaded = await files.upload(new Blob(['hello']), 'hello.txt');
 * const page = await files.list({ source: 'user_upload' });
 * ```
 */
export class SessionFiles {
  constructor(
    private readonly client: Client,
    readonly sessionId: string,
  ) {}

  /**
   * Upload bytes as a session file. `filename` is what the browser sees when
   * the file is later attached to a page.
   */
  async upload(file: Blob | Uint8Array, filename = 'file'): Promise<SessionFile> {
    const response = await uploadSessionFile({
      client: this.client,
      path: { session_id: this.sessionId },
      body: { file: toFile(file, filename) },
      throwOnError: true,
    });
    return response.data;
  }

  /** List the session's non-expired files, newest first. */
  async list(options: FileListOptions = {}): Promise<SessionFilesPage> {
    const response = await listSessionFiles({
      client: this.client,
      path: { session_id: this.sessionId },
      query: { limit: options.limit ?? 100, offset: options.offset ?? 0, source: options.source },
      throwOnError: true,
    });
    return response.data;
  }

  /**
   * Find a file's metadata by ID by scanning the session listing. Rejects with
   * `FileNotFoundError` when the ID is unknown or expired.
   */
  async metadata(fileId: string): Promise<SessionFile> {
    let offset = 0;
    while (true) {
      const page = await this.list({ limit: METADATA_PAGE_SIZE, offset });
      const match = page.files.find(file => file.id === fileId);
      if (match) {
        return match;
      }
      offset += page.files.length;
      if (offset >= page.total || page.files.length === 0) {
        throw new FileNotFoundError(`File ${fileId} was not found in session ${this.sessionId}`);
      }
    }
  }

  /** Download a file's bytes as a `Blob`. */
  async download(fileId: string): Promise<Blob> {
    const response = await downloadSessionFile({
      client: this.client,
      path: { session_id: this.sessionId, file_id: fileId },
      parseAs: 'blob',
      throwOnError: true,
    });
    return response.data as Blob;
  }

  /** Stream a file's bytes. Used by `RemoteFileStorage.download()` to write to disk without buffering. */
  async stream(fileId: string): Promise<ReadableStream<Uint8Array>> {
    const response = await downloadSessionFile({
      client: this.client,
      path: { session_id: this.sessionId, file_id: fileId },
      parseAs: 'stream',
      throwOnError: true,
    });
    const body = response.data as ReadableStream<Uint8Array> | null;
    if (!body) {
      throw new NotteError(`Download of file ${fileId} returned no body`);
    }
    return body;
  }

  /** Delete a session file. */
  async delete(fileId: string): Promise<void> {
    await deleteSessionFile({
      client: this.client,
      path: { session_id: this.sessionId, file_id: fileId },
      throwOnError: true,
    });
  }
}

/**
 * File storage bound to a session, the counterpart of Python's
 * `RemoteFileStorage`. Create it unbound and pass it to `client.Session({ storage })`
 * so the session binds it on start, or bind it yourself with a session ID.
 *
 * ```ts
 * const storage = new RemoteFileStorage(client, sessionId);
 * const uploaded = await storage.upload('./resume.pdf');
 * const localPath = await storage.download(uploaded.id, './downloads');
 * ```
 */
export class RemoteFileStorage {
  private _sessionId: string | null;

  constructor(
    readonly client: NotteClient,
    sessionId?: string,
  ) {
    this._sessionId = sessionId ?? null;
  }

  /** Bind the storage to a session. Called by `Session.start()` when the storage was passed to the session. */
  setSessionId(sessionId: string): void {
    this._sessionId = sessionId;
  }

  /**
   * Bind this storage once, cloning it when another session already owns it.
   *
   * ```ts
   * const first = storage.forSession('session-a'); // first === storage
   * const second = storage.forSession('session-b'); // a clone sharing the client
   * ```
   */
  forSession(sessionId: string): RemoteFileStorage {
    if (this._sessionId === null) {
      this._sessionId = sessionId;
      return this;
    }
    if (this._sessionId === sessionId) {
      return this;
    }
    return new RemoteFileStorage(this.client, sessionId);
  }

  /** ID of the bound session. Throws `InvalidRequestError` while the storage is unbound. */
  get sessionId(): string {
    if (this._sessionId === null) {
      throw new InvalidRequestError('A session ID is required for every file operation');
    }
    return this._sessionId;
  }

  /** Whether the storage has been bound to a session yet. */
  get isBound(): boolean {
    return this._sessionId !== null;
  }

  private files(): SessionFiles {
    return new SessionFiles(this.client.getClient(), this.sessionId);
  }

  /**
   * Upload a file to the session. A string is read as a local path and its
   * basename becomes the uploaded filename unless `uploadFileName` is set.
   *
   * ```ts
   * await storage.upload('./data/resume.pdf');
   * await storage.upload(Buffer.from('hello'), 'hello.txt');
   * ```
   */
  async upload(file: UploadableFile, uploadFileName?: string): Promise<SessionFile> {
    const files = this.files();
    if (typeof file === 'string') {
      const info = await stat(file).catch(() => null);
      if (!info?.isFile()) {
        throw new InvalidRequestError(`Cannot upload file ${file}: it is not a file`);
      }
      const bytes = await readFile(file);
      return files.upload(bytes, uploadFileName ?? basename(file));
    }
    const filename = uploadFileName ?? (file instanceof File ? file.name : 'file');
    return files.upload(file, filename);
  }

  /**
   * List the session's files.
   *
   * ```ts
   * const downloads = await storage.list({ source: 'session_download', limit: 1000 });
   * ```
   */
  async list(options: FileListOptions = {}): Promise<SessionFilesPage> {
    return this.files().list(options);
  }

  /** Metadata of a file by ID. Rejects with `FileNotFoundError` when unknown. */
  async metadata(fileId: string): Promise<SessionFile> {
    return this.files().metadata(fileId);
  }

  /**
   * Download a file to `<localDir>/<filename>` and return the local path. The
   * file is written atomically (temporary file + rename). Rejects with
   * `FileExistsError` when the destination exists unless `force` is set.
   *
   * ```ts
   * const path = await storage.download(fileId, './downloads', { force: true });
   * ```
   */
  async download(fileId: string, localDir = '.', options: FileDownloadOptions = {}): Promise<string> {
    const files = this.files();
    const metadata = await files.metadata(fileId);
    const safeName = sanitizeFilename(metadata.filename);
    if (safeName === '' || safeName === '.' || safeName === '..') {
      throw new NotteError(`Unsafe filename returned for file ${fileId}: ${JSON.stringify(metadata.filename)}`);
    }
    await mkdir(localDir, { recursive: true });
    const destination = join(localDir, safeName);
    const exists = await stat(destination).then(() => true, () => false);
    if (exists && !options.force) {
      throw new FileExistsError(`${destination} already exists; pass force: true to overwrite it`);
    }

    const body = await files.stream(fileId);
    // Unpredictable name plus O_EXCL: a pre-planted symlink is never followed.
    const temporary = join(localDir, `.${safeName}.${randomBytes(8).toString('hex')}.part`);
    try {
      await pipeline(
        Readable.fromWeb(body as unknown as NodeReadableStream<Uint8Array>),
        createWriteStream(temporary, { flags: 'wx' }),
      );
      await rename(temporary, destination);
    } catch (error) {
      await rm(temporary, { force: true });
      throw error;
    }
    return destination;
  }

  /** Download a file's bytes as a `Blob` without touching the local filesystem. */
  async downloadBlob(fileId: string): Promise<Blob> {
    return this.files().download(fileId);
  }

  /** Delete a session file. */
  async delete(fileId: string): Promise<void> {
    await this.files().delete(fileId);
  }
}
