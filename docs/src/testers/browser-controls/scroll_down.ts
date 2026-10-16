// @sniptest filename=scroll_down.ts
// @sniptest show=1-11
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session();
await session.use(async () => {
  // Create a page tall enough to scroll.
  await session.evaluateJs("document.body.innerHTML = '<main style=\"height:300vh\">Scroll demo</main>'");
  await session.execute({ type: "scroll_down", selector: "html" });
  console.log("Moved down: " + await session.evaluateJs("String(window.scrollY > 0)"));
});

const status = await session.status();

export { status };
