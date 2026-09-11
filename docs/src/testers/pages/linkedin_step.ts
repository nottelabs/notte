import { NotteClient } from 'notte-sdk';

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

await client.Session().use(async (page) => {
  const url = 'https://www.linkedin.com/';

  // Observe page and take a step
  await page.execute({ type: 'goto', url });
  let actions = await page.observe({ instructions: "click 'jobs'" });
  let result = await page.execute(actions[0]);
  console.log(result.message);

  // Another one
  actions = await page.observe({ instructions: 'dismiss the sign in check' });
  result = await page.execute(actions[0]);
  console.log(result.message);
});
