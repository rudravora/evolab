# n8n phone approvals: build guide

Contract source: `docs/API.md` section 11 (Integrations) and
`docs/ARCHITECTURE.md` section 3.6 (Approvals). Read those first if
anything here seems to disagree with them — they are the source of truth,
this is the build guide.

Two small flows:

1. **Approval flow** — receives `approval_requested`, sends a Telegram
   message with Approve/Reject buttons, calls back into the backend.
2. **Run-finished flow** — receives `run_finished` (and optionally
   `job_failed`), sends a plain notification, no buttons.

Both are triggered by the same outbound webhook (`N8N_WEBHOOK_URL`); the
flow branches on the `event` field in the body.

## Prerequisites (names only, no secrets)

| Credential / setting | Used for | Where it comes from |
|---|---|---|
| `N8N_SIGNING_SECRET` | verifying `X-Signature` on the inbound webhook | same value set in the backend's `.env` (see `.env.example`) |
| A Telegram Bot API credential in n8n | sending the approval/notification message | create a bot via `@BotFriend`/`@BotFather` in Telegram, store the bot token as an n8n credential named e.g. `evolab-telegram-bot` |
| A Telegram chat id | which chat the bot posts into | the researcher's own chat with the bot (send it one message first, then read the chat id from `getUpdates` or n8n's Telegram node setup helper) |
| The backend's public base URL | building `decision_url` is not needed — API.md's outbound payload already includes a full `decision_url` per decision, so n8n never has to construct it itself |

## Flow 1: Approval (approval_requested)

### Nodes, in order

1. **Webhook** (trigger node)
   - HTTP Method: `POST`
   - Path: pick something like `evolab/n8n-inbound` (this is n8n's *inbound*
     webhook URL, i.e. the value you put in the backend's `N8N_WEBHOOK_URL`
     — not to be confused with the backend's own inbound hook,
     `/hooks/n8n/decide`, which n8n calls *outbound* from a later node in
     this same flow)
   - Respond: "Using Respond to Webhook Node" (so we control the response
     after signature verification, not immediately)

2. **Code** node (`Verify signature`)
   - Compute `hmac_sha256(N8N_SIGNING_SECRET, raw_request_body)` and compare
     against the `X-Signature` header (format `sha256=<hex>`), using a
     constant-time comparison.
   - n8n's Code node has access to `$input.first().json` for the parsed
     body and `$request.headers` for headers; to HMAC over the *raw* body
     bytes exactly as received (not n8n's re-serialized JSON, which could
     differ in key order/whitespace from what the backend signed), either:
     - enable "Raw Body" on the Webhook node and HMAC that raw string, or
     - `VERIFY`: confirm with the backend dev (A) whether the signature is
       computed over the exact byte-for-byte request body or over a
       canonical JSON re-serialization — this guide assumes raw bytes,
       which is the safer and more common convention, but API.md does not
       say explicitly.
   - On mismatch, set a flag (e.g. `$json.signatureValid = false`) and
     continue to the next node rather than throwing, so the flow can still
     respond cleanly.

3. **If** node (`Signature valid?`)
   - True branch → continue to step 4.
   - False branch → **Respond to Webhook** node returning `401` with a
     short JSON body like `{"ok": false, "reason": "bad signature"}`, then
     stop. (This is n8n's own response to the backend's outbound call, not
     a path defined in API.md — API.md doesn't specify what n8n should
     return to the backend on a bad signature, since delivery is "best
     effort and never blocks a run"; returning 401 here is a reasonable
     default a sibling call can check, not a contract requirement.)

4. **Switch** node (`event`)
   - Branch on `{{$json.event}}`: `approval_requested` → this flow;
     `run_finished` / `job_failed` → Flow 2 (below); anything else → a
     fallback branch that just logs and responds 200 (future event types
     must not break this flow, per API.md section 13's "clients must
     ignore unknown fields and unknown SSE event types" forward-compat
     rule, which this guide extends to unknown webhook `event` values too).

5. **Telegram** node (`Send approval message`)
   - Credential: the Telegram bot credential above.
   - Chat ID: the stored chat id.
   - Text: build from `{{$json.summary}}`, `{{$json.type}}`,
     `{{$json.run_id}}`, e.g.:
     ```
     Approval needed: {{$json.type}}
     {{$json.summary}}
     Run: {{$json.run_id}}
     Expires: {{$json.expires_at}}
     ```
   - Reply markup: inline keyboard, two buttons:
     - `✅ Approve` → `callback_data` = a short string your Code node can
       parse back, e.g. `approve:{{$json.approval_id}}` (Telegram
       `callback_data` is capped at 64 bytes, so don't put the full token
       in it — see step 7)
     - `❌ Reject` → `callback_data` = `reject:{{$json.approval_id}}`
   - Before this node, use a **Set** node to stash
     `{{$json.decisions.approve.token}}` and
     `{{$json.decisions.reject.token}}` plus both `decision_url` values
     somewhere your later nodes can still read them (n8n workflow static
     data, or a tiny key-value store/Redis node, keyed by `approval_id`) —
     the callback only carries `approval_id` and which button was tapped,
     not the token itself, so the token must be looked up at decide-time,
     not threaded through Telegram's callback payload.

6. **Respond to Webhook** node — `200 {"ok": true}` back to the backend, so
   this first leg of the flow finishes (receiving + sending the Telegram
   message). The button tap is a **separate** incoming trigger (step 7).

7. **Telegram Trigger** node (a second trigger, separate execution of this
   same workflow or imported as its own sub-workflow — n8n's Telegram
   Trigger node listens for `callback_query` updates)
   - Parse `callback_data` → `action` (`approve`/`reject`) and
     `approval_id`.
   - Look up the stored token for that `approval_id` + `action` (from
     wherever step 5 stashed it).
   - If no stored token is found (expired from your own store, or an
     unrecognized `approval_id`), answer the callback query with a message
     like "This approval is no longer available" and stop — don't call the
     backend with a token you don't have.

8. **HTTP Request** node (`Call decide hook`)
   - Method: `POST`
   - URL: the `decision_url` for that action (already a full URL per
     API.md's outbound payload — same value for every decision in
     practice, `https://<backend>/api/v1/hooks/n8n/decide`, but use the one
     from the payload rather than hardcoding it, in case that ever
     changes).
   - Body:
     ```json
     { "approval_id": "{{$json.approval_id}}", "decision": "{{$json.action}}", "token": "{{$json.token}}" }
     ```
   - On `200`, answer the Telegram callback with "Approved" / "Rejected".
   - On `403`, the token was invalid, already used, or expired (API.md
     section 11) — answer the callback with "This decision could not be
     recorded (already decided or expired)." Do not retry.

9. **Respond/Answer callback query** — always acknowledge the Telegram
   callback (Telegram requires this within a few seconds or it shows a
   loading spinner to the user), regardless of which branch above was hit.

## Flow 2: run_finished (and job_failed)

Much simpler — no buttons, no callback leg.

1. Reuse the same **Webhook** + **Verify signature** + **Switch** nodes
   from Flow 1 (this can be the same n8n workflow with a second branch off
   the Switch node, or a separate workflow if you'd rather keep them
   decoupled — this guide assumes the same workflow, one Switch).
2. **Telegram** node (`Send run-finished message`)
   - Text for `run_finished`:
     ```
     Run finished: {{$json.run_id}}
     Status: {{$json.status}}
     {{$json.summary}}
     ```
   - Text for `job_failed`:
     ```
     Job failed in run {{$json.run_id}}
     Job: {{$json.job_id}} — {{$json.status}}
     {{$json.summary}}
     ```
   - No reply markup (no buttons needed).
3. **Respond to Webhook** — `200 {"ok": true}`.

## Exporting the flow

In the n8n UI: select all nodes (Ctrl/Cmd+A) → right-click → **Download**
(or **Copy**, then paste into a file) → save as `docs/n8n/workflow.json`.
That file is the n8n-native workflow export format (a JSON object with
`nodes` and `connections` arrays) — commit it alongside this README so a
teammate can re-import it with n8n's **Import from File**.

`VERIFY`: this guide assumes n8n Cloud or a self-hosted n8n reachable at a
stable URL for the Webhook node's public endpoint (n8n needs to be
internet-reachable, or tunneled, for the backend's outbound POST to reach
it) — exact hosting choice wasn't specified in any doc read for this task.

`VERIFY`: whether the backend expects a `200` response body in any
particular shape from n8n's webhook receiver, beyond "delivery is best
effort and never blocks a run" (API.md section 11) — not specified; this
guide's `{"ok": true}` is a reasonable placeholder, not a contract
requirement.
