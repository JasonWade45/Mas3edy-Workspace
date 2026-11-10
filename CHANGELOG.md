# Changelog

All notable changes to N.O.V.A AI. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.1.1] — 2026-11-10

### Fixed
- **Dark mode now covers every widget**, not just custom cards: buttons,
  inputs, selects (and their dropdown menus), text areas, number inputs,
  expanders, dataframes/tables, popovers and tooltips all render from design
  tokens in both light and dark mode.
- Sidebar nav items: transparent background, start-aligned, muted text; hover
  = surface-2; active = accent tint with an inline-start accent bar.
- Secondary buttons: outline style; tertiary buttons: text-only ghost style.
- Quick start actions: single responsive grid (auto-fit, equal cells).
- Recent activity: custom token-styled table (5 rows, relative timestamps,
  "View all" link).
- Approved folders metric shows an "Add an approved folder" action when 0.
- Hero subtitle now meets WCAG AA on the hero background in both themes.

### Changed
- **Token-first theming**: `theme.css` carries all components and reads only
  tokens; `theme-dark.css` now contains *only* token overrides (~30 lines).
  New tokens: `--surface-2`, `--border-strong`, `--accent-soft`,
  `--accent-on-soft`, `--accent-hover`, `--accent-contrast`, `--ring`, plus
  semantic `--success`/`--warning`/`--danger`. All pairs verified WCAG AA
  (4.5:1 body text, 3:1 UI boundaries) with automated contrast tests.
- Provider status dots use token classes instead of inline colors.

## [1.1.0] — 2026-11-10

### Added
- **Tasks page** — local task list (manual add, checkbox done, undo, delete,
  "from chat" badge). Replaces the placeholder tab.
- **Dashboard** — hero value proposition, north-star metric (tasks done in 7
  days), dismissible onboarding card, "خطتي اليوم" daily-plan form,
  "حاسبة تحليل الصفقة" (MAO = ARV×0.70 − repairs), quick actions
  «موجز الصباح» and «المراجعة الأسبوعية».
- **Chat** — compact toolbar with Settings/Privacy/Shortcuts popovers,
  export-to-Markdown download, live context-window meter, ready-made prompt
  templates, `/plan` `/summarize` `/translate` `/followup` slash commands,
  per-assistant actions (Regenerate, Save-as-reference, Convert-to-task,
  thumbs feedback → audit).
- **Streaming replies** (opt-in, `stream_responses`) — tool-free replies only;
  tool agents stay one-shot.
- **PII redaction** (opt-in, `pii_redaction`) — emails, phones, and Luhn-valid
  card numbers masked before any provider call.
- **Rate-limit fallback** — on HTTP 429, up to 2 sibling models from the same
  provider are tried automatically (`model_fallback`, default on).
- **Dialect control** — Egyptian / Gulf / MSA reply dialect; **domain packs** —
  Egyptian real-estate context bundle (`domain_pack`).
- **Theme system** — `theme-dark.css`, light/dark/auto selector persisted in
  config; IBM Plex Sans Arabic + Inter fonts; design tokens (`--fs-*`,
  `--space-*`, `--shadow-*`); reduced-motion, focus-visible, coarse-pointer,
  and print media support; Google-Fonts import.
- **Settings** — per-provider connection test, streaming/PII/fallback/Arabic-
  numerals toggles, dialect picker, domain-pack picker, "فحص النظام والصحة"
  (versions, paths, recent audit rows, demo-data seeding).
- **Analytics** — 7-day audit-event counts.
- **Web reader** — one-click "احفظ في قاعدة المعرفة".
- **Storage** — `seed_demo_data()`, `audit_counts_since()`,
  `list_chats_detailed` now exposes chat `mode`; backups kept-7 rolling.
- **Docs & CI** — STRATEGY.md, ARCHITECTURE.md, this changelog, GitHub
  Actions CI (`python -m unittest test`). 44 tests.

### Fixed
- `tools=None` is now passed explicitly for models without tool support
  (was silently omitted, breaking explicit capability overrides).
- Assistant call failures keep the message and offer Retry instead of
  discarding it.
- Custom-instructions bounds test now reflects the declared 4,000-char cap.

### Changed
- Sidebar rebuilt as compact rail + full panel (icon quick-jump, pinned chats,
  grouped history, chat/code routing, pin toggle, import from ChatGPT/Claude
  exports).
- Chat page heading removed; everything lives in the toolbar now.

## [1.0.0] — initial
- Bilingual workspace, BYO-key providers, guarded files, web reader, local
  memory, knowledge base, backups, audit log.
