import { NotteClient } from 'notte-sdk';

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

const images = await client.scrape('https://example.com/gallery', {
  only_images: true,
});

for (const image of images) {
  console.log(`URL: ${image.url}`);
  console.log(`Description: ${image.description}`);
}
