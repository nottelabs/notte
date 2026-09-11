// puppeteer_script.js
const puppeteer = require('puppeteer-core');

async function main() {
  // Get CDP URL from command line argument
  const cdpUrl = process.argv[2];

  // Connect to Notte session
  const browser = await puppeteer.connect({
    browserWSEndpoint: cdpUrl
  });

  // Get the page (Notte sessions have one default page)
  const pages = await browser.pages();
  const page = pages[0];

  // Use Puppeteer API
  await page.goto('https://example.com');
  console.log('Title:', await page.title());

  await page.screenshot({ path: 'screenshot.png' });

  await browser.disconnect();
}

main().catch(console.error);
