import assert from "node:assert/strict";
import test from "node:test";

import { api, cleanErr } from "../src/lib/api.js";

function fakeBridge() {
  const calls = [];
  return {
    calls,
    toast: (...a) => calls.push(["toast", ...a]),
    showLogin: () => calls.push(["showLogin"]),
    refreshMe: () => calls.push(["refreshMe"]),
  };
}
function respond(status, body) {
  return async () => ({
    status,
    ok: status >= 200 && status < 300,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
  });
}

test("returns parsed JSON and serialises a json option", async () => {
  let seen;
  const bridge = fakeBridge();
  const r = await api(
    "/api/x",
    { method: "POST", json: { a: 1 } },
    {
      bridge,
      fetch: async (p, o) => {
        seen = [p, o];
        return respond(200, { ok: true })();
      },
    },
  );
  assert.deepEqual(r, { ok: true });
  assert.equal(seen[0], "/api/x");
  assert.equal(seen[1].method, "POST");
  assert.equal(seen[1].body, '{"a":1}');
  assert.equal(seen[1].headers["Content-Type"], "application/json");
  assert.equal("json" in seen[1], false);
  assert.deepEqual(bridge.calls, []);
});

test("empty body parses to {}", async () => {
  assert.deepEqual(await api("/api/x", undefined, { bridge: fakeBridge(), fetch: respond(200, "") }), {});
});

test("error message comes from detail", async () => {
  await assert.rejects(
    api("/api/x", undefined, { bridge: fakeBridge(), fetch: respond(400, { detail: "a name is required" }) }),
    { message: "a name is required" },
  );
  await assert.rejects(
    api("/api/x", undefined, { bridge: fakeBridge(), fetch: respond(404, {}) }),
    { message: "We couldn't find what you were looking for." },
  );
  await assert.rejects(
    api("/api/x", undefined, { bridge: fakeBridge(), fetch: respond(500, "<html>boom") }),
    { message: "<html>boom" },
  );
});

test("401 sends the user to sign-in with a session toast", async () => {
  const bridge = fakeBridge();
  await assert.rejects(api("/api/api-tokens", undefined, { bridge, fetch: respond(401, {}) }), {
    message: "Please sign in",
  });
  assert.deepEqual(bridge.calls[0], ["showLogin"]);
  assert.equal(bridge.calls[1][0], "toast");
  assert.deepEqual(bridge.calls[1][2], { type: "info", title: "Session expired" });
});

test("401 on /api/auth/ does not redirect", async () => {
  const bridge = fakeBridge();
  await assert.rejects(api("/api/auth/me", undefined, { bridge, fetch: respond(401, { detail: "bad code" }) }), {
    message: "bad code",
  });
  assert.deepEqual(bridge.calls, []);
});

test("403 shows Not allowed and refreshes identity", async () => {
  const bridge = fakeBridge();
  await assert.rejects(api("/api/api-tokens", undefined, { bridge, fetch: respond(403, {}) }), {
    message: "not permitted",
  });
  assert.deepEqual(bridge.calls[0][2], { type: "err", title: "Not allowed" });
  await new Promise((r) => setTimeout(r, 5));
  assert.deepEqual(bridge.calls.at(-1), ["refreshMe"]);
});

test("network errors show the Can't reach the server toast", async (t) => {
  t.mock.method(console, "error", () => {});
  const bridge = fakeBridge();
  await assert.rejects(
    api("/api/x", undefined, {
      bridge,
      fetch: async () => {
        throw new TypeError("Failed to fetch");
      },
    }),
    { message: "Can't reach the server — please check your connection and try again." },
  );
  assert.match(bridge.calls[0][1], /^Can't reach the server\./);
  assert.deepEqual(bridge.calls[0][2], { type: "err", title: "Connection problem" });
});

test("cleanErr strips httpx noise", () => {
  assert.equal(
    cleanErr("Client error '404 Not Found' for url 'http://x/y'\nFor more information check: https://mdn"),
    "404 Not Found",
  );
  assert.equal(cleanErr("", 429), "Too many requests — please wait a moment and try again.");
  assert.equal(cleanErr(null, 418), "Request failed (418). Please try again.");
});
