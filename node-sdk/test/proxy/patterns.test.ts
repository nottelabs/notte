import { describe, it, expect } from 'vitest';
import { validatePath, DEFAULT_ALLOWED_PATTERNS } from '@/proxy/patterns';

describe('validatePath', () => {
  describe('directory traversal prevention', () => {
    it('should reject paths with ".."', () => {
      const result = validatePath(['..', 'etc', 'passwd'], DEFAULT_ALLOWED_PATTERNS);
      expect(result.isValid).toBe(false);
      expect(result.error).toContain('directory traversal');
    });

    it('should reject paths with "//"', () => {
      const result = validatePath(['sessions//start'], DEFAULT_ALLOWED_PATTERNS);
      expect(result.isValid).toBe(false);
      expect(result.error).toContain('directory traversal');
    });

    it('should reject paths starting with "/"', () => {
      const result = validatePath(['/sessions', 'start'], DEFAULT_ALLOWED_PATTERNS);
      expect(result.isValid).toBe(false);
      expect(result.error).toContain('directory traversal');
    });
  });

  describe('valid session paths', () => {
    it('should allow sessions list', () => {
      expect(validatePath(['sessions'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow sessions/start', () => {
      expect(validatePath(['sessions', 'start'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow sessions/{id}', () => {
      expect(validatePath(['sessions', 'abc-123'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow sessions/{id}/stop', () => {
      expect(validatePath(['sessions', 'abc-123', 'stop'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow sessions/{id}/page/observe', () => {
      expect(validatePath(['sessions', 'abc-123', 'page', 'observe'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow sessions/{id}/page/execute', () => {
      expect(validatePath(['sessions', 'abc-123', 'page', 'execute'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow sessions/{id}/page/scrape', () => {
      expect(validatePath(['sessions', 'abc-123', 'page', 'scrape'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow sessions/{id}/page/screenshot', () => {
      expect(validatePath(['sessions', 'abc-123', 'page', 'screenshot'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow sessions/{id}/debug', () => {
      expect(validatePath(['sessions', 'abc-123', 'debug'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow sessions/{id}/replay', () => {
      expect(validatePath(['sessions', 'abc-123', 'replay'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });
  });

  describe('valid agent paths', () => {
    it('should allow agents list', () => {
      expect(validatePath(['agents'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow agents/start', () => {
      expect(validatePath(['agents', 'start'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow agents/{id}', () => {
      expect(validatePath(['agents', 'agent-123'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow agents/{id}/stop', () => {
      expect(validatePath(['agents', 'agent-123', 'stop'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow agents/{id}/workflow/code', () => {
      expect(validatePath(['agents', 'agent-123', 'workflow', 'code'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });
  });

  describe('valid vault paths', () => {
    it('should allow vaults list', () => {
      expect(validatePath(['vaults'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow vaults/create', () => {
      expect(validatePath(['vaults', 'create'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow vaults/{id}/credentials', () => {
      expect(validatePath(['vaults', 'vault-123', 'credentials'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow vaults/{id}/card', () => {
      expect(validatePath(['vaults', 'vault-123', 'card'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });
  });

  describe('valid function paths', () => {
    it('should allow functions list', () => {
      expect(validatePath(['functions'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow functions/{id}/runs/start', () => {
      expect(validatePath(['functions', 'fn-123', 'runs', 'start'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow functions/{id}/runs/{run_id}', () => {
      expect(validatePath(['functions', 'fn-123', 'runs', 'run-456'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow functions/{id}/fork', () => {
      expect(validatePath(['functions', 'fn-123', 'fork'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow functions/{id}/schedule', () => {
      expect(validatePath(['functions', 'fn-123', 'schedule'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });
  });

  describe('valid persona paths', () => {
    it('should allow personas list', () => {
      expect(validatePath(['personas'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow personas/create', () => {
      expect(validatePath(['personas', 'create'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow personas/{id}/emails', () => {
      expect(validatePath(['personas', 'p-123', 'emails'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow personas/{id}/sms', () => {
      expect(validatePath(['personas', 'p-123', 'sms'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });
  });

  describe('valid session file paths', () => {
    it('should allow sessions/{id}/files', () => {
      expect(validatePath(['sessions', 'sess-123', 'files'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow sessions/{id}/files/{file_id}', () => {
      expect(validatePath(['sessions', 'sess-123', 'files', 'file-id'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should reject removed global storage paths', () => {
      expect(validatePath(['storage', 'uploads'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(false);
    });
  });

  describe('valid root/misc paths', () => {
    it('should allow health', () => {
      expect(validatePath(['health'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow scrape', () => {
      expect(validatePath(['scrape'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow scrape_from_html', () => {
      expect(validatePath(['scrape_from_html'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow anything/start', () => {
      expect(validatePath(['anything', 'start'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow usage', () => {
      expect(validatePath(['usage'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow usage/logs', () => {
      expect(validatePath(['usage', 'logs'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });

    it('should allow prompts/improve', () => {
      expect(validatePath(['prompts', 'improve'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(true);
    });
  });

  describe('invalid paths', () => {
    it('should reject unknown endpoints', () => {
      const result = validatePath(['unknown', 'endpoint'], DEFAULT_ALLOWED_PATTERNS);
      expect(result.isValid).toBe(false);
      expect(result.error).toContain('does not match any allowed endpoint pattern');
    });

    it('should reject admin-only endpoints not in the OpenAPI spec', () => {
      expect(validatePath(['metrics'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(false);
      expect(validatePath(['flamegraph'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(false);
      expect(validatePath(['bua'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(false);
      expect(validatePath(['bua', 'completions'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(false);
      expect(validatePath(['health', 'sessions'], DEFAULT_ALLOWED_PATTERNS).isValid).toBe(false);
    });
  });

  describe('custom patterns', () => {
    it('should validate against custom patterns', () => {
      const customPatterns = [/^custom\/endpoint$/];
      expect(validatePath(['custom', 'endpoint'], customPatterns).isValid).toBe(true);
      expect(validatePath(['sessions', 'start'], customPatterns).isValid).toBe(false);
    });
  });
});
