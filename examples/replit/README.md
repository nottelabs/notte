# Notte for Replit Agent

Connect Replit Agent to Notte's hosted MCP server. No browser installation or Replit API token is needed.

Open [Replit Integrations](https://replit.com/integrations), choose **+ Add MCP server**, and enter:

| Field | Value |
| --- | --- |
| Display name | `Notte` |
| MCP server URL | `https://api.notte.cc/mcp` |
| Advanced header name | `Authorization` |
| Advanced header value | `Bearer <your-notte-api-key>` |

Create your API key at [Notte](https://console.notte.cc/apikeys), enter it in Replit's header field, and select **Test & save**. Keep the key out of source files, chat prompts, and shared URLs.

`server.json` contains the public installation settings. With Node.js 24+, run `npm run install-link` to produce a shareable Replit setup link. It contains no credentials; add authentication in Replit after opening it.

Ask Agent to use Notte to start one browser, open `https://example.com`, read its title, and stop that browser on success or error. Reuse the browser ID returned by Notte and keep stop instructions in follow-up tasks.

For maintainers, `npm ci`, `npm test`, and `npm run test:live` verify the installation link and hosted MCP contract. Live tests require `NOTTE_API_KEY`; `NOTTE_API_URL` selects another environment. They create only their own browsers and independently verify closure. Hosted Replit Agent execution has not been tested.

Replit's [official MCP setup guide](https://docs.replit.com/build/connect-via-mcp) describes the native connector and custom headers.
