# Telegram Notifications (Item 5a) — Design Spec

Roadmap item 5 (see `docs/superpowers/plans/2026-08-13-forexcast-foundation.md`):
Telegram + email in-app linking and dispatch, consuming the "fired" state
item 3's alert evaluation already writes. Builds on the Phase 1 design
spec's [§7 Notifications](2026-08-13-forex-predictor-design.md) section.

## 0. Scope split: 5a (Telegram) now, 5b (Email) next

Item 5's two channels are less coupled than they first look: `alert_events`
dispatch and message-building are shared, but Telegram's delivery
mechanism (a bot API + a linking flow) and email's (a transactional email
provider + a verification flow) are otherwise independent, and Telegram
alone is already a complete, useful feature — a user can rely on it
without email configured at all. This project has consistently shipped
its more complex features incrementally (2a before 2b/2c, item 3 before
item 4) rather than as one large increment, and the same reasoning
applies here: splitting keeps each spec/plan small, each independently
testable, and lets the shared dispatch-loop infrastructure get built and
proven once (in 5a) before a second channel adapter (5b) layers onto it.
5b picks up right after 5a ships, reusing `alert_events`/message-building
and adding only the email-specific pieces (a transactional email provider,
`notification_settings.email_verified` verification flow).

This spec covers **5a: Telegram only.**

## 1. No new backend routes

Unlike item 4, item 5a needs zero new FastAPI routes. The Telegram linking
flow's first step — generating a one-time connect code — is a plain
random string with an expiry, no different in kind from any other
user-owned row the frontend already writes directly via Supabase RLS
(`alerts`, `llm_settings`). `notification_settings` already has owner
insert/update RLS from `0001_init_schema.sql`, so item 6 (frontend, out of
scope here) writes `telegram_link_code` + `telegram_link_code_expires_at`
directly, the same way it already will write `alerts` rows and (per item
4) `llm_settings` rows. This follows item 3's established precedent: no
new backend route unless a concrete reason forces one, and holding the
Telegram bot token (a secret) plus running with no per-request user JWT
at all (it's a scheduled job, not a request) is exactly what makes the
*second* half of linking — matching an incoming Telegram message to a
code and writing back `telegram_chat_id` — backend/job work, not route
work.

## 2. Schema changes

Two additive columns, no new tables:

```sql
alter table public.alert_events
    add column notified_at timestamptz;

alter table public.notification_settings
    add column telegram_link_code text,
    add column telegram_link_code_expires_at timestamptz;
```

`alert_events.notified_at` (nullable, default null) is this job's
dispatch cursor — `notified_at is null` means "not yet sent," set once
successfully dispatched. The two `notification_settings` columns hold the
in-flight linking code; both go null again once linking succeeds (no
lingering stale code sitting around after use).

## 3. Telegram linking — stateless polling, no new table for offset tracking

The bot needs a `TELEGRAM_BOT_TOKEN` (free via @BotFather, no card) — a
new `Settings.telegram_bot_token: str = ""` field (defaults to `""` per
this project's standing rule after 2b's incident with a required field
with no default breaking every entrypoint).

Telegram's `getUpdates` API is itself the state store: calling it with no
`offset` returns every update not yet acknowledged; calling it again with
`offset = <highest update_id seen> + 1` acknowledges (clears) everything
up to that point from Telegram's server-side queue. So `process_telegram_links()`
needs no persisted cursor of its own:

1. Call `getUpdates` (no offset) — returns pending updates since the last
   ack (across possibly-multiple prior runs, if a run crashed before
   acking; Telegram holds unacked updates up to 24h, which is more than
   enough headroom for a job that runs every few minutes).
2. For each update containing a message matching `/start <code>`: look up
   `notification_settings` where `telegram_link_code = <code>` and
   `telegram_link_code_expires_at > now()`. A match writes
   `telegram_chat_id = <update's chat id>`, `telegram_linked_at = now()`,
   and clears both code columns. No match (expired, already consumed, or
   simply not a linking message) is a silent no-op — a stray Telegram
   message reaching the bot is a normal, expected occurrence, not an
   error.
3. Call `getUpdates` once more with `offset = <highest update_id from
   step 1> + 1` to ack, even though the response is (usually) empty — this
   is the acknowledgment call, not a data call.

If the job crashes between steps 1 and 3, the next run simply reprocesses
the same updates — safe, because matching a code is idempotent (an
already-consumed code no longer matches any row, so reprocessing the same
`/start <code>` message a second time is just another silent no-op).

## 4. Alert dispatch

`dispatch_pending_alerts()`:

1. Fetch `alert_events` where `notified_at is null` (a new accessor,
   `get_unnotified_alert_events()`).
2. For each, fetch its parent `alerts` row (existing-shape query, matching
   this codebase's established one-fetch-then-related-fetch style rather
   than introducing PostgREST embedding for the first time) to get
   `user_id`, `base_code`, `quote_code`.
3. Fetch that user's `notification_settings` row. If there's no
   `telegram_chat_id` (never linked, or unlinked), skip this event without
   marking it notified — the same "genuinely nothing to do yet" skip
   pattern as 2c's fewer-than-3-articles case, not an error, and not
   permanently discarded either: if the user links Telegram later, this
   spec deliberately leaves the event `notified_at is null` so a later run
   picks it up and still delivers it, rather than silently losing alerts
   fired before linking completed.
4. Build a human-readable message from `alert_events.details` (already
   written by item 3 — see its two known shapes below) and the pair.
5. Send via Telegram's `sendMessage` API. A send failure (network,
   4xx/5xx from Telegram) propagates and fails the job loudly — matches
   this project's standing fail-loud-on-genuine-infrastructure-failure
   philosophy; a single alert_event that keeps failing to send blocks that
   iteration but (per the same isolation pattern 2c/3 already use) must
   not prevent *other* events from being marked/sent — collect errors,
   continue the loop, raise once at the end if any occurred (mirrors
   `run_alert_evaluation`'s existing `errors` list pattern exactly).
6. On success, mark `notified_at = now()`.

**Message shapes** (from `alert_events.details`, written by
`app/recommendations/jobs.py`, unchanged by this spec):

- `alert_type == "threshold"`: `{current_rate, threshold_rate, direction}`
  → `"🔔 USD/EUR crossed {direction} {threshold_rate}: currently {current_rate}"`
- `alert_type == "recommendation_change"`: `{latest, previous}`
  → `"📊 USD/EUR recommendation changed: {previous} → {latest}"`
  (`previous` may be absent from a real payload only in a state this
  project's own `recommendation_changed()` already guards against — item
  3 never records this event type with `previous` missing, so this
  formatter can assume it's present.)

`app/notifications/message.py` holds `build_message(alert, details) ->
str`, taking the joined `alert` dict (for `base_code`/`quote_code`) and
the raw `details` jsonb, isolated from both the Telegram client and the
Supabase accessors so it's independently testable and 5b can reuse it
verbatim for email bodies.

## 5. File structure

```
backend/app/notifications/
    __init__.py
    telegram_client.py   # send_message(chat_id, text), get_updates(offset), send/getUpdates HTTP calls
    message.py           # build_message(alert, details) -> str
    supabase_rest.py      # get_unnotified_alert_events, get_alert, get_notification_settings,
                          #   link_telegram, mark_alert_event_notified
    jobs.py               # process_telegram_links(), dispatch_pending_alerts(), run_notifications()
    cli.py                 # matches every other module's __main__ entrypoint pattern
```

`.github/workflows/notify.yml`: a new cron, every 5 minutes (`*/5 * * * *`)
— tighter than every other job's daily cadence, deliberately: a user
actively linking Telegram in Settings expects near-immediate confirmation,
not a next-day wait, and `notified_at`-gated dispatch means a tighter
cadence costs nothing extra (an idle run with nothing pending is a cheap
no-op, same as 2c's per-currency skip costing nothing when there's
nothing to skip). `workflow_dispatch` trigger for manual runs, `env:`
block routes `SUPABASE_URL`/`SUPABASE_SERVICE_KEY`/`TELEGRAM_BOT_TOKEN`
from secrets, no `${{ }}` in any `run:` shell body (this project's
standing workflow-authoring rule), `working-directory: backend`.

## 6. Testing

- No live network calls in the automated suite — every Telegram API call
  mocked (`httpx.get`/`post`), matching every prior module.
- `test_notifications_telegram_client.py`: `send_message`/`get_updates`
  request shape, propagate on non-2xx.
- `test_notifications_message.py`: both `alert_type` shapes format
  correctly; a `recommendation_change` payload is trusted to have
  `previous` present (see §4) — no defensive test for its absence, since
  nothing upstream can produce that shape.
- `test_notifications_supabase_rest.py`: each accessor, mocked httpx.
- `test_notifications_jobs.py`: `process_telegram_links` matches/expires/
  no-ops correctly; `dispatch_pending_alerts` skips an unlinked user
  without marking notified, sends+marks for a linked one, isolates one
  failing send from the rest (collect-errors-raise-at-end, mirroring
  `test_recommendation_jobs.py`'s existing pattern for
  `run_alert_evaluation`).
- Final task: live verification — trigger `notify.yml` manually, actually
  link a real Telegram account via the bot, fire a real threshold alert
  (reusing this project's own already-live data), confirm the message
  arrives.

## 7. Deferred (explicitly out of scope for 5a)

- Email channel entirely — 5b, next.
- The Settings-page UI for the "link Telegram" button, deep link
  construction (needs `TELEGRAM_BOT_USERNAME`, which only the frontend
  needs — not added to backend `Settings` since backend never constructs
  the deep link) — item 6.
- Notification preferences (e.g. "only notify me for ACT NOW, not
  VOLATILE") — no such granularity exists anywhere in this app yet
  (alerts are all-or-nothing per the `alerts` table today); revisit only
  if item 6's UI surfaces a real request for it.
- Rate-limiting a chatty user's own alerts (e.g. capping notifications per
  hour) — not asked for, and `alert_events` is already naturally bounded
  by how often item 3's job actually detects real firings.
