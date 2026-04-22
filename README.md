# Job Search Report Automation

A cloud-first, config-driven Node.js + TypeScript project that generates job-search reports from a single JSON configuration file.

## Why this project exists

Searching for remote jobs across many sources is repetitive and noisy. This project creates deterministic, reviewable reports so teams and AI agents can track results over time with clean diffs.

## Features

- JSON config is the **single source of truth**.
- Multiple reports generated from one config file.
- Pluggable search providers (`mock`, `browser`, `api`).
- Deterministic query builder and filtering pipeline.
- URL canonicalization + deduplication.
- Explainable scoring and rejection reasons.
- Markdown + JSON output per search.
- Auto-generated report index (`reports/README.md`).
- Change-aware file writing (avoid CI noise).
- Dry-run and debug modes for safe cloud execution.
- Ready for GitHub Actions and future UI/screenshot workflows.

## Setup

```bash
npm install
npm run build
```

## Config format

Default config file: `./searches.json`  
Schema file: `./searches.schema.json`

Each search includes:

- `id`
- `title`
- `filename`
- `sites`
- `include`
- `exclude`
- `allOf`
- `anyOf`
- `noneOf`
- `maxResults`

## Run searches

```bash
npm run search
npm run search -- --config=./searches.json
npm run search -- --provider=api --debug
npm run search:dry
```

### Runtime modes

- **Normal mode**: executes provider, filters, and writes outputs.
- **Debug mode (`--debug`)**: emits intermediate reasoning and rejection detail.
- **Dry-run mode (`--dry-run`)**: plans execution but does not write files.

## Generated outputs

- Markdown reports: `reports/*.md`
- JSON datasets: `reports/json/*.json`
- Main index: `reports/README.md`

## Provider architecture

Main pipeline depends only on `SearchProvider` interface:

- `ApiSearchProvider` (default, performs real web search via DuckDuckGo Lite HTML endpoint)
- `BrowserSearchProvider` (currently delegates to API provider; reserved for full Playwright crawling)
- `MockSearchProvider` (deterministic fixtures for tests/cloud runs)


## Real search behavior

By default, the CLI now uses `--provider=api`, which performs real network search requests.

Optional environment override:

- `SEARCH_ENGINE_URL` (default: `https://lite.duckduckgo.com/lite/`)

Examples:

```bash
npm run search
npm run search -- --provider=api --config=./searches.json
SEARCH_ENGINE_URL=https://lite.duckduckgo.com/lite/ npm run search
```

## Add or modify searches

1. Update `searches.json`.
2. Validate with `npm run test`.
3. Execute `npm run search`.
4. Commit only changed report artifacts.

## Future UI plan

`/apps/web` is reserved for a future UI that can:

- list report index entries
- open individual report views
- filter by tags/domain/location/search type
- render visual previews backed by generated JSON

## Future screenshot validation plan

Placeholder scripts are wired now:

- `npm run preview` serves `reports/`
- `npm run screenshot` runs Playwright and captures images under `artifacts/screenshots`

This enables future screenshot regression checks with minimal changes.

## GitHub Actions readiness

The architecture is workflow-ready for scheduled runs:

1. checkout
2. install dependencies
3. run search pipeline
4. run tests/lint
5. commit only changed report files
6. upload artifacts (reports/screenshots) if needed

## Scripts

- `npm run build`
- `npm run dev`
- `npm run search`
- `npm run search:dry`
- `npm run test`
- `npm run lint`
- `npm run format`
- `npm run preview`
- `npm run screenshot`

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for project structure, coding rules, testing guidance, and extension patterns.
