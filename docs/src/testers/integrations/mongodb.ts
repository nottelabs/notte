// @sniptest filename=notte_mongodb.ts
// @sniptest typecheck_only=true
import { MongoClient, MongoServerError } from 'mongodb';
import { NotteClient } from 'notte-sdk';

const url = 'https://example.com';
export const result = await new NotteClient().Session({ max_duration_minutes: 3 }).use(async (session) => {
  try {
    const mongo = new MongoClient(process.env.MONGODB_URI!, { timeoutMS: 10_000 });
    try {
      const collection = mongo.db(process.env.MONGODB_DATABASE || 'notte')
        .collection(process.env.MONGODB_COLLECTION || 'pages');
      await session.execute({ type: 'goto', url });
      const inserted = await collection.insertOne({
        url, markdown: await session.scrape(), session_id: session.getId()!,
      });
      console.log(inserted.insertedId.toHexString());
      return { document_id: inserted.insertedId.toHexString(), session_id: session.getId()! };
    } finally {
      await mongo.close();
    }
  } catch (error) {
    const code = error instanceof MongoServerError && typeof error.code === 'number' ? error.code : undefined;
    throw new Error(`MongoDB export failed (session ${session.getId()!}, code ${code})`);
  }
});
