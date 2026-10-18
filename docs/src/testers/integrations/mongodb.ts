// @sniptest filename=notte_mongodb.ts
// @sniptest typecheck_only=true
import { MongoClient, MongoServerError } from 'mongodb';
import { NotteClient } from 'notte-sdk';

const url = 'https://example.com';
const uri = process.env.MONGODB_URI;
if (!uri) throw new Error('Set MONGODB_URI before running this example');

export const result = await new NotteClient().Session({ max_duration_minutes: 3 }).use(async (session) => {
  let stage = 'MongoDB connection';
  try {
    const mongo = new MongoClient(uri, { timeoutMS: 10_000, serverSelectionTimeoutMS: 10_000 });
    let documentId: string;
    let cleanupFailed = false;
    try {
      await mongo.connect();
      const collection = mongo.db(process.env.MONGODB_DATABASE || 'notte')
        .collection(process.env.MONGODB_COLLECTION || 'pages');
      stage = 'browser navigation';
      await session.execute({ type: 'goto', url });
      stage = 'browser scrape';
      const markdown = await session.scrape();
      stage = 'MongoDB insert';
      const inserted = await collection.insertOne({ url, markdown, session_id: session.getId()! });
      console.log(inserted.insertedId.toHexString());
      documentId = inserted.insertedId.toHexString();
    } finally {
      try {
        await mongo.close();
      } catch {
        cleanupFailed = true;
      }
    }
    if (cleanupFailed) {
      stage = 'MongoDB cleanup';
      throw new Error('MongoDB disconnect failed');
    }
    return { document_id: documentId, session_id: session.getId()! };
  } catch (error) {
    const code = error instanceof MongoServerError && typeof error.code === 'number' ? error.code : undefined;
    const type = error instanceof Error ? error.name : 'UnknownError';
    throw new Error(`MongoDB export failed (session ${session.getId()!}, code ${code}): ${stage}: ${type}`);
  }
});
