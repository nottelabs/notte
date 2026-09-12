// @sniptest filename=match_viewport.ts
// @sniptest show=1-11
import { NotteClient } from "notte-sdk";

const client = new NotteClient();

// Desktop
const desktop = client.Session({ viewport_width: 1920, viewport_height: 1080 });
await desktop.use(async () => {});

// Laptop
const session = client.Session({ viewport_width: 1366, viewport_height: 768 });
await session.use(async () => {});

const status = await session.status();
const desktopStatus = await desktop.status();
if (
  status.viewport_width !== 1366 ||
  status.viewport_height !== 768 ||
  desktopStatus.viewport_width !== 1920 ||
  desktopStatus.viewport_height !== 1080
) {
  throw new Error("Viewport configuration mismatch");
}
const results = [desktopStatus.session_id, status.session_id];
export { status, results };
