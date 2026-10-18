import { main, type createToken } from "../src/index.js";

// The parent supplies only the local HTTP fixture's dummy proxy data.
main(async () => ({
  token: "fixture-token",
  proxy: JSON.parse(process.env.EVERVAULT_FIXTURE_PROXY!) as Awaited<ReturnType<typeof createToken>>["proxy"],
})).catch(() => { process.exitCode = 1; });
