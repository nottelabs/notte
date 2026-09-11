// Only main content (excludes navbars, footers, sidebars)
const markdown = await client.scrape(url, { only_main_content: true }); // Default

// Include all page content
const fullMarkdown = await client.scrape(url, { only_main_content: false });
