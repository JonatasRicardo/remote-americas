# Contributing Guide

## Project structure

- `src/config`: config loading and validation
- `src/query`: deterministic search query construction
- `src/search`: provider interface and implementations
- `src/normalize`: raw result normalization + URL canonicalization
- `src/filters`: rule matching, deduping, acceptance/rejection
- `src/scoring`: explainable relevance scoring
- `src/generators`: markdown/json/index output rendering
- `src/pipeline`: orchestration for one search and all searches
- `src/utils`: logging, file writing, time/text helpers
- `tests/unit`: fast logic tests
- `tests/integration`: pipeline behavior tests
- `tests/fixtures`: deterministic provider data
- `apps/web`: future UI placeholder
- `playwright`: screenshot workflow placeholder

## Coding rules

- Keep modules small and explicit.
- Prefer pure functions for domain logic.
- Keep I/O logic in pipeline/utils boundaries.
- Avoid hidden behavior and global state.
- Keep logs concise and structured.
- Do not hardcode search definitions in source files.


## Current provider status

- `ApiSearchProvider` is the default runtime provider and performs real web search requests.
- `BrowserSearchProvider` currently delegates to API provider while full browser crawling is pending.
- `MockSearchProvider` is used for deterministic tests and offline development.

## How to add a new provider

1. Implement `SearchProvider` in `src/search/`.
2. Keep credentials/config in environment variables.
3. Return `RawSearchResult[]` only.
4. Add provider selection wiring in `src/index.ts`.
5. Add tests with fixtures or mocks.

## How to add a new report type

1. Extend schema/types if format changes.
2. Add generator under `src/generators`.
3. Wire into `run-search.ts`.
4. Add/adjust tests for output and stats.

## Run quality checks

```bash
npm run lint
npm run test
npm run build
```

## Validate generated outputs

```bash
npm run search
npm run preview
npm run screenshot
```

Use `npm run search:dry` to validate query/filter logic without writing files.
