// Include links (default)
const markdownWithLinks = await client.scrape(url, { scrape_links: true });

// Exclude links
const markdownWithoutLinks = await client.scrape(url, { scrape_links: false });

// Include images in markdown
const markdownWithImages = await client.scrape(url, { scrape_images: true });

// Exclude images (default)
const markdownWithoutImages = await client.scrape(url, { scrape_images: false });
