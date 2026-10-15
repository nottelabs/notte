// @sniptest filename=scroll_up.ts
// @sniptest show=1-11
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session();
await session.use(async () => {
  // Create a page tall enough to scroll.
  await session.evaluateJs("document.body.innerHTML = '<main style=\"height:300vh\">Scroll demo</main>'");
  await session.execute({ type: "scroll_down", selector: "html" });
  await session.execute({ type: "scroll_up", selector: "html" });
});

const status = await session.status();

export { status };
