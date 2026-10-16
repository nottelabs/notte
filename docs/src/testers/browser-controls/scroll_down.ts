// @sniptest filename=scroll_down.ts
// @sniptest show=1-18
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session();
await session.use(async () => {
  // Create a page tall enough to scroll.
  await session.evaluateJs(`(() => {
    document.open();
    document.write('<!doctype html><main>Scroll demo</main>');
    document.close();
    document.body.style.margin = '0';
    document.querySelector('main').style.height = '300vh';
    return document.documentElement.scrollHeight;
  })()`);
  await session.execute({ type: "scroll_down" });
  console.log("Moved down: " + await session.evaluateJs("String(window.scrollY > 0)"));
});

const status = await session.status();

export { status };
