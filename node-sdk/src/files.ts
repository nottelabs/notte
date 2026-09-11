import type { Client } from '@/lib/client/client/types.gen';

// These endpoints ship in this SDK before they are available in staging's
// generated OpenAPI client. Keep their public response types beside the
// handwritten wrapper so regenerating against staging remains deterministic.
export type FileSource = 'user_upload' | 'session_download';

export type SessionFile = {
  id: string;
  session_id: string;
  filename: string;
  mime_type: string;
  size: number;
  checksum: string;
  created_at: string;
  expires_at: string;
  source: FileSource;
};

export type SessionFilesPage = {
  files: SessionFile[];
  total: number;
  limit: number;
  offset: number;
};

export class SessionFiles {
  constructor(private readonly client: Client, private readonly sessionId: string) {}

  private path(fileId?: string): string {
    const root = `/sessions/${encodeURIComponent(this.sessionId)}/files`;
    return fileId ? `${root}/${encodeURIComponent(fileId)}` : root;
  }

  async upload(file: Blob, filename = 'file'): Promise<SessionFile> {
    const body = new FormData();
    body.append('file', file, filename);
    const result = await this.client.request<SessionFile>({
      method: 'POST',
      url: this.path(),
      body,
    });
    if (result.error || !result.data) throw new Error('Failed to upload session file');
    return result.data as unknown as SessionFile;
  }

  async list(options: { source?: FileSource; limit?: number; offset?: number } = {}): Promise<SessionFilesPage> {
    const result = await this.client.request<SessionFilesPage>({
      method: 'GET',
      url: this.path(),
      query: { limit: options.limit ?? 100, offset: options.offset ?? 0, source: options.source },
    });
    if (result.error || !result.data) throw new Error('Failed to list session files');
    return result.data as unknown as SessionFilesPage;
  }

  async download(fileId: string): Promise<Blob> {
    const result = await this.client.request<Blob>({
      method: 'GET',
      url: this.path(fileId),
      parseAs: 'blob',
    });
    if (result.error || !result.data) throw new Error(`Failed to download session file ${fileId}`);
    return result.data as Blob;
  }

  async delete(fileId: string): Promise<void> {
    const result = await this.client.request({ method: 'DELETE', url: this.path(fileId) });
    if (result.error) throw new Error(`Failed to delete session file ${fileId}`);
  }
}
