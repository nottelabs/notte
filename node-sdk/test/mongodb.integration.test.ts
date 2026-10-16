import { execFile } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { MongoClient, ObjectId } from 'mongodb';
import { describe, expect, it } from 'vitest';
import { NotteClient } from '@/index';
import { expectSessionClosed } from './helpers/session-closure';

const execute = promisify(execFile);
const languages = ['python', 'typescript'] as const;

function recipe(language: typeof languages[number], collection: string) {
  for (const name of ['NOTTE_API_KEY', 'NOTTE_API_URL', 'MONGODB_URI']) {
    if (!process.env[name]) throw new Error(`Set ${name} explicitly`);
  }
  const python = process.env.NOTTE_DOCS_PYTHON;
  if (language === 'python' && !python) throw new Error('Set NOTTE_DOCS_PYTHON with pymongo==4.19.0');
  const example = fileURLToPath(new URL(`../../docs/src/testers/integrations/mongodb.${language === 'python' ? 'py' : 'ts'}`, import.meta.url));
  const runner = fileURLToPath(new URL(`../../docs/src/sniptest/run_${language}.${language === 'python' ? 'py' : 'mjs'}`, import.meta.url));
  return execute(language === 'python' ? python! : process.execPath,
    language === 'python' ? [runner, example] : ['--experimental-strip-types', runner, example], {
      env: { ...process.env, MONGODB_DATABASE: 'notte_integration_tests', MONGODB_COLLECTION: collection },
      timeout: 120_000, maxBuffer: 2 * 1024 * 1024,
    });
}

describe.skipIf(process.env.NOTTE_MONGODB_LIVE !== '1')('MongoDB documentation', () => {
  it.each(languages)('persists the %s scrape and closes its browser', async language => {
    const uri = process.env.MONGODB_URI;
    if (!uri || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(uri).hostname)) {
      throw new Error('Use an explicit loopback MONGODB_URI for the isolated integration database');
    }
    const name = `notte_recipe_${randomUUID().replaceAll('-', '')}`;
    const mongo = new MongoClient(uri, { timeoutMS: 10_000 });
    const collection = mongo.db('notte_integration_tests').collection(name);
    try {
      let stdout: string;
      try {
        ({ stdout } = await recipe(language, name));
      } catch {
        throw new Error(`${language} MongoDB recipe failed (SDK output withheld)`);
      }
      const { result } = JSON.parse(stdout.trim().split(/\r?\n/).at(-1)!) as {
        result: { document_id: string; session_id: string };
      };
      await expectSessionClosed(new NotteClient(), result.session_id, `MongoDB ${language}`);
      const stored = await collection.findOne({ _id: new ObjectId(result.document_id) });
      expect(stored).toMatchObject({ url: 'https://example.com', session_id: result.session_id });
      expect(stored?.markdown).toContain('Example Domain');
      expect(await collection.countDocuments()).toBe(1);
    } finally {
      try { await collection.drop(); } finally { await mongo.close(); }
    }
  }, 150_000);

  it.each(languages)('closes the %s browser when MongoDB rejects the document', async language => {
    const uri = process.env.MONGODB_URI;
    if (!uri || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(uri).hostname)) {
      throw new Error('Use an explicit loopback MONGODB_URI for the isolated integration database');
    }
    const name = `notte_recipe_${randomUUID().replaceAll('-', '')}`;
    const mongo = new MongoClient(uri, { timeoutMS: 10_000 });
    const database = mongo.db('notte_integration_tests');
    const collection = database.collection(name);
    try {
      await database.createCollection(name, { validator: { required_for_test: { $exists: true } } });
      let output = '';
      try {
        await recipe(language, name);
        throw new Error('MongoDB unexpectedly accepted the invalid document');
      } catch (error) {
        const failure = error as { stdout?: string; stderr?: string };
        output = `${failure.stdout ?? ''}\n${failure.stderr ?? ''}`;
      }
      // Code 121 comes from the real MongoDB server's document validator.
      const sessionId = output.match(/MongoDB export failed \(session ([0-9a-f-]{36}), code 121\)/i)?.[1];
      if (!sessionId) throw new Error(`${language} did not report the owned browser after a MongoDB validation error (SDK output withheld)`);
      expect(output).toContain('MongoDB insert:');
      await expectSessionClosed(new NotteClient(), sessionId, `MongoDB ${language} failure`);
      expect(await collection.countDocuments()).toBe(0);
    } finally {
      try { await collection.drop(); } finally { await mongo.close(); }
    }
  }, 150_000);
});
