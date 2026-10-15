# Example validation backlog

Run `python docs/src/sniptest/parity.py` for current pairing and execution counts. `parity.json` records Python examples awaiting a TypeScript counterpart; `testers/snippets.json` records individual scripts awaiting type checks or owned execution fixtures. These are different gaps.

Do not remove an execution exemption until the script has a behavior assertion, bounded resource use, and cleanup for every resource it creates. The catalog and parity checks prevent the exemption backlog from growing.

## Remaining work

- Use controlled pages to verify structured extraction, missing fields, filtering, images, and link placeholders.
- Give agent examples bounded step limits and owned vault/persona fixtures, and check their answers and cleanup.
- Verify cookie, recording, and file artifacts without overwriting user files.
- Test external-provider and Puppeteer examples with isolated dependencies and credentials.
- Keep Python Function-runtime handlers separate from caller SDK examples. Do not imply that Functions execute TypeScript.

## SDK differences

Python exposes notebook and CDP viewer helpers that differ from the Node viewer. Python's Function timeout is an idle read timeout in seconds; Node's `timeoutMs` is a whole-call deadline in milliseconds. File storage is automatically available on Python sessions; attach `client.FileStorage()` explicitly in Node.

Document these differences rather than inventing equivalent APIs or weakening checks. Prefer the supported `idle_timeout_minutes` parameter over its legacy alias, and set `max_duration_minutes` when increasing the idle timeout beyond the default session lifetime.
