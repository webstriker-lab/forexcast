# LLM Agent — Design Spec

Roadmap item 4 (see `docs/superpowers/plans/2026-08-13-forexcast-foundation.md`):
multi-provider adapter, tool-calling, chat. Builds on the Phase 1 design
spec's [§6 LLM Agent](2026-08-13-forex-predictor-design.md) section, which
already fixed the provider list, the tool list, and the "keys stored
encrypted per-user" requirement. This spec fills in the implementation
details that section left open.

Scope split from the roadmap doc: item 4 is backend-only (the `/chat`
endpoint and its tool-calling machinery). Item 6 (Dashboard UI) owns the
actual chat *panel* — the input box, message list, and Settings page for
entering a provider/API key. Item 4 exists so item 6 has something to call.

## 1. Why backend-only, and why a new route

Item 3 (recommendation engine) deliberately added no new backend API
routes — the frontend reads `predictions`/`recommendations` straight from
Supabase via RLS, and that precedent holds through item 6 unless a
concrete reason forces a route. Chat is that reason: turning a user's
message into a grounded answer requires holding their (decrypted) LLM API
key server-side and running a multi-step tool-calling loop — neither is
safe or practical to do from the browser. So item 4 introduces exactly one
new authenticated route, `POST /chat`, following the existing
`get_current_user` JWT pattern from `app/auth.py` (already used by
`/me`).

## 2. Per-user API key storage — reusing `llm_settings`

`supabase/migrations/0001_init_schema.sql` already defines:

```sql
create table public.llm_settings (
    user_id uuid primary key references auth.users (id) on delete cascade,
    provider text not null check (provider in ('gemini', 'openai', 'deepseek', 'groq', 'openrouter')),
    api_key_encrypted text not null,
    model text,
    updated_at timestamptz not null default now()
);
```

RLS already grants the owner select/insert/update on their own row — the
same shape as `alerts`, where the frontend writes directly with the user's
own JWT rather than going through a backend endpoint. That's a strong
signal of the original intent, and item 4 follows it: **no new
settings endpoints**. The frontend (item 6) will insert/update this row
directly via the Supabase client, encrypting the key client-side before
it ever leaves the browser.

That requires asymmetric encryption, not the symmetric approach 2c used
for server-side provider config (`OPENROUTER_API_KEY` etc., which only
the backend ever touches). Concretely: **PyNaCl's `SealedBox`**.

- A keypair is generated once (`nacl.public.PrivateKey.generate()`) and
  committed as two secrets: `LLM_SETTINGS_PRIVATE_KEY` (backend-only env
  var, base64) and a corresponding public key that item 6's frontend
  bakes into its build config the same way it already bakes in
  `VITE_SUPABASE_URL` — no endpoint needed to serve it, since a public
  key isn't secret and doesn't need to be rotatable via API for an app
  at this scale.
- Frontend (item 6, out of scope here) does
  `nacl.sealedbox.seal(apiKeyBytes, publicKey)` client-side, base64s the
  result, and writes it into `api_key_encrypted` alongside `provider` and
  optional `model` via a normal RLS-scoped upsert.
- Backend decrypts with `SealedBox(PrivateKey(...))` only at the moment
  it needs to call the LLM for that user's chat turn — the plaintext key
  never touches any table or log, and lives in memory for the duration of
  one request.
- Because the owner can still `select` their own row (RLS unchanged),
  a future Settings UI can show "provider: openai, key configured" by
  checking `api_key_encrypted is not null`, without the backend ever
  being involved.

`app/agent/crypto.py` holds the one function this needs:
`decrypt_api_key(ciphertext_b64: str) -> str`, raising a clear `ValueError`
if `LLM_SETTINGS_PRIVATE_KEY` is unset or decryption fails (corrupted
ciphertext, wrong key) — fail loud, this is a config/integrity problem,
not a normal-operation branch.

Two new `config.py` fields: `llm_settings_private_key: str = ""` and
`pynacl` added to `requirements.txt`.

## 3. Provider adapter

All five providers in `llm_settings`'s check constraint expose an
OpenAI-compatible `/chat/completions` endpoint with `tools`/`tool_calls`
support — including Gemini, via its
`https://generativelanguage.googleapis.com/v1beta/openai/` compatibility
endpoint. That means one HTTP call shape covers all five; the only
per-provider variable is `base_url` and a default model:

```python
# app/agent/providers.py
PROVIDERS = {
    "openai":     {"base_url": "https://api.openai.com/v1", "default_model": "gpt-4o-mini"},
    "deepseek":   {"base_url": "https://api.deepseek.com/v1", "default_model": "deepseek-chat"},
    "groq":       {"base_url": "https://api.groq.com/openai/v1", "default_model": "llama-3.3-70b-versatile"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "default_model": "openai/gpt-oss-20b:free"},
    "gemini":     {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "default_model": "gemini-2.0-flash"},
}
```

`call_chat_completion(provider, api_key, model, messages, tools) -> dict`
POSTs to `{base_url}/chat/completions` with the standard OpenAI body
shape (`messages`, `tools`, `tool_choice: "auto"`), `Authorization: Bearer
{api_key}` header, and the same retry-on-429 linear backoff
(`MAX_RETRIES = 3`, `RETRY_BACKOFF_SECONDS = 5`) already reviewed and
shipped in `news/llm_client.py` — copied here rather than imported, since
`news/llm_client` is tied to the server-side forced-provider/OpenRouter-
fallback config and this is a genuinely different call site (per-user
provider, no fallback — if a user's chosen provider is down, that's
surfaced to them, not silently swapped).

Returns the raw parsed JSON response body; the orchestrator (below) is
responsible for interpreting `choices[0].message`.

## 4. Tools

The seven tools fixed by the Phase 1 spec, each a plain Python function
with a JSON-schema tool definition alongside it:

- **`get_forecast(quote_code, horizon_days)`** — wraps
  `prediction/supabase_rest.py`'s existing predictions read path (base is
  always `USD`, confirmed live — every row in `predictions` has
  `base_code = 'USD'`, so tools take a single currency code, not a pair).
  Returns `predicted_rate`, `lower_bound`, `upper_bound`, `confidence`, or
  a clear "no forecast available for X" message if none exists — the
  model should say that, not invent a number.
- **`get_news_summary(quote_code)`** — wraps
  `news/supabase_rest.get_latest_news_sentiment` (already same-day-only by
  design from 2c). Returns `score`, `summary`, `article_count`, or "no
  news sentiment scored today for X".
- **`get_recommendation(quote_code)`** — needs a new
  `get_latest_recommendation(quote_code)` accessor added to
  `recommendations/supabase_rest.py` (the table is public-read, same
  pattern as `get_latest_predictions`). Returns `recommendation`,
  `current_rate`, `expected_rate`, bounds, `generated_at`.
- **`create_alert(quote_code, alert_type, threshold_rate=None, direction=None)`**,
  **`list_alerts()`**, **`update_alert(alert_id, ...)`**,
  **`delete_alert(alert_id)`** — user-scoped CRUD on the existing `alerts`
  table. New accessors in `recommendations/supabase_rest.py`, each taking
  `user_id` explicitly and filtering `?user_id=eq.<id>` server-side via
  the service-role client (mirroring the currency-scoped filtering
  already used throughout the codebase) — the chat endpoint's own JWT
  auth establishes `user_id`; tools never trust a user_id argument from
  the model itself. `update_alert`/`delete_alert` additionally verify the
  target alert's `user_id` matches before acting, returning a "not found"
  tool result (not a 404 or exception) if it doesn't, since a user asking
  about an alert that isn't theirs is a normal conversational dead-end,
  not an error.

All read tools return `None`/empty-shaped data rather than raising when
data is simply absent (no forecast yet, no news today) — matches the
existing "missing data is a normal outcome" convention from 2b/2c. Tools
only raise for genuine infrastructure failure (Supabase unreachable),
which propagates and fails the chat turn loudly, same as every other job
in this codebase.

## 5. Orchestrator — the tool-calling loop

`app/agent/orchestrator.py`, one function:
`run_chat(user_id: str, messages: list[dict]) -> dict`.

1. Load `llm_settings` for `user_id`. If no row exists, raise a
   `LLMNotConfiguredError` (→ 400 at the route level with a message
   pointing at Settings) — this is a normal first-time-user state, not a
   server error.
2. Decrypt the API key (§2).
3. Prepend a system message grounding the assistant: it has access to
   live forecast/news/recommendation/alert tools, must call them rather
   than guess numbers, and should say plainly when data isn't available
   rather than inventing it — directly enforcing the Phase 1 spec's "its
   answers are grounded in the actual tool outputs, never invented"
   requirement.
4. Loop up to `MAX_TOOL_ITERATIONS = 5`:
   - Call the provider with the running message list + tool schemas.
   - If the response has no `tool_calls`, that's the final answer —
     return it.
   - Otherwise, execute each requested tool call. A tool call with
     arguments that fail JSON parsing or schema validation gets a
     `role: "tool"` error message fed back to the model (e.g. `"invalid
     arguments: missing quote_code"`) so the model can retry with
     corrected arguments — self-correcting within the loop, matching the
     "isolate one bad thing, don't kill the whole turn" pattern from 2c's
     LLM-response-parsing (`score_sentiment` returning `None` on
     unparseable output rather than crashing the job). A genuine
     exception from a tool itself (Supabase down) still propagates and
     fails the whole request — that's real infrastructure failure, not a
     model mistake.
   - Append the tool results and loop again.
5. If `MAX_TOOL_ITERATIONS` is exhausted without a final answer, raise
   `ToolLoopExceededError` (→ 502-ish response) rather than looping
   forever or silently truncating — fail loud, this indicates either a
   confused model or a tool-schema bug worth surfacing, not something to
   paper over.

## 6. Route

`app/routers/chat.py`:

```
POST /chat
Authorization: Bearer <supabase JWT>   (via existing get_current_user)
Body:  {"messages": [{"role": "user"|"assistant", "content": str}, ...]}
200:   {"message": {"role": "assistant", "content": str}, "tool_calls": [{"tool": str, "arguments": dict, "result": ...}]}
400:   LLMNotConfiguredError (no llm_settings row)
422:   FastAPI's own request-validation error on a malformed body (e.g. an invalid `role` value, now constrained to "user"/"assistant" per Fix 6 above)
502:   ToolLoopExceededError (MAX_TOOL_ITERATIONS exhausted)
```

Only those two custom exceptions are caught and mapped explicitly. Any
other exception (decrypt failure, a genuine `httpx` error from the
provider surviving its own retries, Supabase unreachable) is left
unhandled and surfaces as FastAPI's default 500 — consistent with this
codebase's fail-loud philosophy: those are real infrastructure/config
problems, not conditions worth a friendlier status code that could mask
them.

`tool_calls` is included in every response (empty list if none were made)
so the future chat UI can show what the agent actually checked — makes
"grounded in tool outputs" visible, not just true.

**Chat is stateless** (YAGNI): no server-side conversation-history table.
The frontend holds the message array (in-memory, optionally
`localStorage` for reload continuity) and resends the full history each
turn, same as a typical chat API. This is the one place this spec
deliberately does less than it could — a persisted-threads table is easy
to add later if item 6 turns out to need it (e.g. "show my past
conversations"), and adding it speculatively now would mean designing
RLS and pagination for a feature nothing yet asks for.

## 7. Testing

- `test_agent_providers.py` — mocked `httpx.post` per provider (base_url
  selection, retry-on-429 mirroring the existing GDELT/LLM retry tests).
- `test_agent_crypto.py` — round-trip encrypt(via a test-only PyNaCl
  `SealedBox.encrypt` using the public half)/decrypt, and the
  missing-private-key / corrupted-ciphertext failure paths.
- `test_agent_tools.py` — each tool with mocked `supabase_rest` accessors:
  happy path, "no data yet" path, and (for alert CRUD) the
  wrong-user-owns-this-alert path.
- `test_agent_orchestrator.py` — mocked provider responses driving the
  loop: no-tool-call (immediate answer), one tool call then answer,
  malformed tool-call arguments (self-correction), and
  `MAX_TOOL_ITERATIONS` exhaustion.
- `test_routers_chat.py` — route-level: 400 when unconfigured, 200 happy
  path with the orchestrator mocked, auth rejection reusing the existing
  `/me` auth test pattern.

No live-provider integration test is possible here the way 2c's GitHub
Actions live-verification worked — there's no free shared credential to
run against in CI, and provider behavior isn't this project's code to
verify. Manual verification (this being built with a real OpenRouter key
already in `backend/.env` from 2c) substitutes: one real chat turn asking
a forecast question, confirming the tool actually gets called and the
answer reflects its result rather than a hallucinated number.

## 8. Deferred (explicitly out of scope for item 4)

- The chat panel UI, Settings page (key entry + provider picker), and
  wiring the frontend's SealedBox public key — all item 6.
- Persisted conversation history — revisit only if item 6 finds a
  concrete need.
- Streaming responses (SSE/websocket) — the free-tier Render backend and
  a single-request tool-calling loop don't need it yet; a plain
  request/response is simpler and this can be upgraded later without
  changing the tool/orchestrator layer.
- Rate-limiting/cost controls on chat usage — each user supplies their
  own API key, so cost is already isolated per-user; nothing here spends
  the app owner's money.
