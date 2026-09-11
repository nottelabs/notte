# TypeScript SDK reference generation

Run from the repository root:

```sh
npm ci --prefix node-sdk
npm run docs:generate --prefix node-sdk
npm run docs:test --prefix node-sdk
npm run docs:check --prefix node-sdk
```

`generate-reference.mjs` uses the installed TypeScript compiler and the SDK's
`tsconfig.json` to discover public high-level classes exported from `src/index.ts`.
It reads signatures, overloads, parameter defaults, accessors, JSDoc, exported
option types, and the transitive source-defined types those APIs reference.
Generated OpenAPI request/response models are included; low-level HTTP transport
implementation types are excluded.
Supporting type pages and Encryption remain generated but are hidden from the
sidebar. The SDK's `ActionSpace.actions` union supplies Core Features / Actions;
other type pages are reachable through related-type links on API pages.
Feature landing pages derive their creation API from `NotteClient` factory
return types and put direct constructors in a collapsed reference section.
Method titles are unqualified; navigation follows task order rather than source
order. Computed iterator hooks are hidden and diagnostic methods live in Debug.
It does not import or execute the SDK, call OpenAPI, or require credentials.

Edit SDK declarations/JSDoc to change API documentation. Generated pages live in
`docs/src/typescript-sdk-reference/`; their navigation group in `docs.json` is
generated too. Existing Python reference pages and URLs are not relocated.
The small class-slug mapping controls presentation only, not which methods exist.

Scope: high-level root-exported classes and related types. Generated HTTP
functions, legacy root helper functions, and proxy subpath entrypoints are not
documented by this generator. Referenced types may be internal source types;
their presence in the reference does not imply a new package export. Missing
JSDoc stays missing rather than being replaced by inferred runtime claims.

`--check` is read-only and fails for missing, modified, or orphaned generated
pages and stale navigation. Normal generation removes orphaned pages only when
they carry this generator's ownership marker; it refuses to overwrite manual
MDX. CI checks the output and compiles every generated page as MDX on Node 22/24.

These are API signatures, not independently maintained executable examples.
Runnable Python/TypeScript examples remain in `docs/src/testers/` and are tested
by the paired-example pipeline.
The Session getting-started page embeds the TypeScript block from the generated
`docs/src/snippets/sessions/index.mdx`, keeping the tested example as its only
code source. After editing that tester, run `python docs/src/sniptest/generate.py`
before `npm run docs:generate --prefix node-sdk`. The guide expands the same
compiler-derived fields as the `SessionOptions` reference and links to the
generated scrape, observe, and execute method pages.
