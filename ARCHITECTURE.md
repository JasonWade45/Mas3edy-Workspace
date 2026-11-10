# N.O.V.A AI — Architecture

Single Streamlit process; no server-side services; all state local.

```
┌────────────────────────────────────────────────────────────┐
│ app.py  (Streamlit UI: sidebar rail, pages, chat toolbar)  │
├─────────────┬──────────────────────────────────────────────┤
│ UI helpers  │ to_arabic_digits · STYLE_TEMPERATURES        │
│ (in-file)   │ slash_commands · compose_system_prompt call  │
├─────────────┴──────────────────────────────────────────────┤
│ core/assistant_core.py   run_assistant()                   │
│   system prompt = base(dialect, domain pack)               │
│                + personalization (memory retrieval)          │
│                + response style                              │
│   tool loop (≤6 rounds): calculate · web_read ·             │
│   list_files/read_file/propose_file_change (approved)       │
├─────────────┬───────────────┬───────────────┬──────────────┤
│ providers   │ redact.py     │ streaming.py  │ domain_packs │
│ (OpenAI-    │ (T1 masking,  │ (SSE-ish text │.py (real-    │
│ compatible, │  Luhn check)  │  deltas)      │ estate Egypt)│
│ BYO key)    │               │               │              │
├─────────────┴───────────────┴───────────────┴──────────────┤
│ core/storage.py   SQLite @ user_data_dir("Mas3edy")         │
│   chats · notes(memory/knowledge/example) · tasks · audit   │
│   backups/ (kept-7 rolling snapshots) · config.json         │
│ core/secrets_store.py   API keys in OS keyring (env fallback)│
└─────────────────────────────────────────────────────────────┘
```

## Data flow — one chat send

1. `st.chat_input` → slash-command expansion (`/plan`, `/summarize`,
   `/translate`, `/followup`) → optional PII redaction copy for outbound.
2. System prompt assembled: dialect suffix (AR only) + domain pack +
   retrieved memory (if personalization on) + response style.
   Temperature from `STYLE_TEMPERATURES[response_style]`.
3. Provider selection: saved provider → model (auto-route picks via
   `select_model_for_task`, else explicit) → optional rate-limit fallback
   (429 → up to 2 sibling models from the same provider, `model_fallback`).
4. Response path: streaming (only when `stream_responses` **and** tools are
   disabled for the model) or one-shot `run_assistant`. Tool agents never
   stream — tool-call JSON must arrive complete to parse safely.
5. Persisted: message pair appended to session + `save_chat` →
   SQLite; `audit("chat_usage", …)` records provider/model for analytics;
   `save_chat` upserts by chat id.

## Storage schema (app data dir, not the repo)

- `assistant.sqlite3` — tables `chats(id, mode[chat|code], title, messages
  JSON, pinned, updated_at)`, `notes(kind CHECK IN
  memory|knowledge|example, …)`, `tasks(title, status[open|done],
  source[manual|chat], created_at, done_at)`,
  `audit(event, detail, created_at)`.
- `config.json` — provider list (no secrets), flags (see STRATEGY.md).
- `backups/` — rolling 7-day snapshots created on startup (best-effort).
- **API keys never touch disk** — system keyring via `keyring`;
  `MAS3EDY_PROVIDER_<NAME>` env var honored as fallback.

## Trust boundaries

| Boundary | Guard |
|---|---|
| Web/file content → prompt | Fenced as untrusted in system prompt; instructions inside content are ignored by policy |
| Model → filesystem | Writes only via `propose_file_change` → human diff approval → `approve_proposal`; no direct writes ever |
| Model → math | AST-whitelisted `calc`; no `eval` |
| Outbound messages | Optional PII redaction (T1) |
| Public web | HTTPS only, public hosts, redirects blocked (`core/network.py`) |
| App → internet | No telemetry, no analytics beacons; `audit` is strictly local |

## Failure modes & degradation

- Provider down / 429 → `RateLimitError` → sibling-model fallback →
  `fallback_notice` toast → on failure, message kept in session with
  retry button (never swallowed).
- Keyring unavailable → env var fallback; save attempts surface a warning.
- SQLite locked/corrupt → startup backup attempt + explicit error toast;
  personalization degrades gracefully (chat still works).
- Stale model list → manual "تحديث قائمة الموديلات" per provider; capability
  mismatches default to "auto".

## Why Streamlit (and its limits)

Zero-build, single-file deploy, RTL-capable via injected CSS. Costs: no
websocket streaming primitive (simulated with `st.write_stream`), no
route-level state (sidebar quick-jump uses `session_state`), no ARIA-perfect
semantics — hence `prefers-reduced-motion`, `:focus-visible`, and
`pointer:coarse` targets in `theme.css`. The React rewrite is a deliberate
v2 question, not a v1 defect.

## Testing

`python -m unittest test` — 44 tests (unit + offline fixtures + AppTest
boot smokes for dashboard/chat/tasks/settings). CI: `.github/workflows/ci.yml`.
