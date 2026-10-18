function diagnostic(error: unknown): string {
  if (error instanceof Error) {
    const fixed = [
      "Set NOTTE_API_KEY",
      "Use an HTTPS Notte API URL",
      "Invalid session response",
      "Browser action failed",
      "The title was not returned",
      "The browser task did not finish",
    ];
    if (
      fixed.includes(error.message) ||
      /^Notte API returned HTTP [1-5][0-9]{2}$/.test(error.message)
    ) {
      return error.message;
    }
    if (error.name === "TimeoutError") return "Notte request timed out";
    if (error.name === "AbortError") return "Notte request aborted";
  }
  return "Unexpected browser task failure";
}

export async function readPage(url = "https://example.com") {
  const apiKey = Deno.env.get("NOTTE_API_KEY");
  const root = Deno.env.get("NOTTE_API_URL") ?? "https://api.notte.cc";
  if (!apiKey) throw new Error("Set NOTTE_API_KEY");
  if (new URL(root).protocol !== "https:") {
    throw new Error("Use an HTTPS Notte API URL");
  }
  async function call<T>(
    path: string,
    method: string,
    body?: unknown,
  ): Promise<T> {
    const response = await fetch(new URL(path, root), {
      method,
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) {
      await response.body?.cancel();
      throw new Error(`Notte API returned HTTP ${response.status}`);
    }
    return await response.json();
  }
  const session = await call<{ session_id: string }>(
    "/sessions/start",
    "POST",
    { max_duration_minutes: 3 },
  );
  if (!/^[0-9a-f-]{36}$/.test(session.session_id)) {
    throw new Error("Invalid session response");
  }
  const path = `/sessions/${session.session_id}`;
  let output: { title: string; session_id: string } | undefined;
  let taskFailed = false;
  let taskError: unknown;
  try {
    for (
      const action of [{ type: "goto", url }, {
        type: "evaluate_js",
        code: "document.title",
      }]
    ) {
      const result = await call<
        { success: boolean; data?: { markdown: string } }
      >(`${path}/page/execute`, "POST", action);
      if (!result.success) throw new Error("Browser action failed");
      if (action.type === "evaluate_js") {
        if (typeof result.data?.markdown !== "string") {
          throw new Error("The title was not returned");
        }
        output = {
          title: result.data.markdown,
          session_id: session.session_id,
        };
        break;
      }
    }
    if (!output) throw new Error("The browser task did not finish");
  } catch (error) {
    taskFailed = true;
    taskError = error;
  }
  try {
    await call(`${path}/stop`, "DELETE");
  } catch (error) {
    console.error("Notte browser cleanup failed:", diagnostic(error));
    if (!taskFailed) throw error;
  }
  if (taskFailed) throw taskError;
  return output!;
}

export default async function handler(request: Request): Promise<Response> {
  if (request.method !== "POST") {
    return new Response("Use POST", {
      status: 405,
      headers: { Allow: "POST" },
    });
  }
  const token = Deno.env.get("NOTTE_VALTOWN_TOKEN");
  if (!token) return new Response("Set NOTTE_VALTOWN_TOKEN", { status: 503 });
  if (request.headers.get("Authorization") !== `Bearer ${token}`) {
    return new Response("Unauthorized", { status: 401 });
  }
  try {
    return Response.json(await readPage());
  } catch (error) {
    console.error("Notte browser task failed:", diagnostic(error));
    return Response.json({ error: "Browser task failed" }, { status: 502 });
  }
}
