# N.O.V.A AI — Strategy

**Vision:** the private, Arabic-first AI workspace for the Egyptian real-estate
operator — your leads, deals, files, and memory stay on your machine; the model
is a replaceable engine you bring your own key for.

## North star

**Tasks completed per active week** (tracked via the `task_done` audit event).
Not messages sent, not tokens — *finished work*. The dashboard shows
"tasks done in the last 7 days" as its first-class metric; everything else is
an input, not an outcome.

## Personas

| Persona | Job to be done | Pain today | N.O.V.A answer |
|---|---|---|---|
| **Broker–owner** (default) | Qualify leads, chase follow-ups, analyze deals between site visits | Cloud assistants that leak client data; English-first tools | Egyptian-dialect chat, PII redaction before send, local task list, MAO calculator |
| **Solo freelancer / consultant** | Draft proposals, emails, meeting notes daily | Paying 3 subscriptions for chat, notes, and a to-do app | One workspace: chat + knowledge notes + tasks + weekly review |
| **Team lead (future)** | Shared playbooks for a sales team | Inconsistent quality across juniors | Domain packs (real estate) embed best practice into every reply — RBAC explicitly out of scope for v1.x |

## MoSCoW (v1.1)

**Must:** private local storage; BYO-key providers (OpenAI-compatible); guarded
file access with human approval; PII redaction toggle; Arabic dialects; tasks
that write themselves from chat; offline-friendly degradation.
**Should:** streaming replies; morning briefing & weekly review prompts; model
rate-limit fallback; export chat as Markdown; context-window meter.
**Could:** voice dictation; calendar sync; multi-agent routing.
**Won't (v1.x):** RBAC, kanban boards, embeddings/RAG over large corpora,
plugin marketplace, reminders/notifications — listed in "Next steps" of the
roadmap because they need infra a local single-user app shouldn't carry.

## Privacy tiers (T0–T3)

| Tier | What lives here | Examples |
|---|---|---|
| **T0 — Local only** | Never leaves the machine | SQLite chats, memory notes, tasks, audit log, config (API keys in system keyring) |
| **T1 — Redacted cloud** | PII masked (emails, phones, card numbers via Luhn) before any provider call | Any chat with `pii_redaction` on |
| **T2 — Full cloud, your key** | Raw content sent to *your* configured provider | File contents you choose to share in a prompt |
| **T3 — Internet egress** | Public HTTPS reads the user explicitly requests | Web reader; `web_read` tool |

Rule: the UI always shows which tier a feature touches; features never mix
tiers silently. PII redaction (T1) is one checkbox in Settings and applies to
outbound messages only — local copies stay intact.

## Feature flags (config.json, all user-controllable)

| Flag | Default | Purpose |
|---|---|---|
| `personalization_enabled` | `true` | Retrieve local memory into the system prompt |
| `response_style` | `متوازن` | Response structure & tone; mapped to temperature preset |
| `stream_responses` | `false` | Live typing effect; auto-off for tool agents |
| `pii_redaction` | `false` | T1 masking before provider calls |
| `model_fallback` | `true` | On 429, try up to 2 sibling models from same provider |
| `arabic_numerals` | `false` | Render digits as ٠١٢٣ in chat |
| `dialect` | `egyptian` | `egyptian` \| `gulf` \| `msa` reply dialect |
| `domain_pack` | `none` | `real_estate` embeds Egyptian market playbooks |
| `onboarding_done` | `false` | Dismiss the first-run checklist |

## Agent sketch (v1.x, honest status)

The assistant today is **tool-augmented chat**, not an autonomous agent:
`run_assistant` loops up to 6 rounds, offering the model `calculate` (AST-safe
math), `web_read`, and — when a working folder is granted — `list_files`,
`read_file`, `propose_file_change` (human-approved diffs only). A real agent
tier (planning, self-review, multi-step task execution with checkpoints) is
the v1.2 north goal; the T1 redaction layer and audit spine it will need
already exist.

## Economics (zero-cost posture)

All features above run on: local SQLite, the system keyring, and the user's
existing provider subscription. The only inherently cloud-priced components are
the model calls themselves — for which BYO-key keeps us out of the billing
loop entirely. No paid SaaS, no hosted DB, no vector-store hosting.
