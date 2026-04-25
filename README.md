# remote-americas

DuckDuckGo web scraper for remote job search terms, with batch execution from JSON and automated updates through GitHub Actions.

## Project structure

- `erp_scraper.py`: main scraper script.
- `data/queries/search_terms.json`: search-term configuration.
- `data/results/*.json`: one JSON output file per search term.
- `.github/workflows/scrape.yml`: daily run plus automatic PR creation when results change.

## Search-term config format

File: `data/queries/search_terms.json`

```json
[
  {
    "title": "Frontend React Remote",
    "queries": [
      "site:job-boards.greenhouse.io \"front-end\" \"react\" \"remote\" -\"green card\"",
      "site:linkedin.com/jobs \"front-end\" \"react\" \"remote\" -\"green card\"",
      "site:dice.com/jobs \"front-end\" \"react\" \"remote\" -\"green card\""
    ],
    "output": "frontend-react-remote"
  }
]
```

Rules:

- Required fields: `title`, `queries`, `output`.
- `queries` must be a non-empty array of strings.
- `output` must be lowercase kebab-case (example: `frontend-react-remote`).
- Output path is always `data/results/<output>.json`.

## Output JSON format

Each result file in `data/results/` is a JSON array:

```json
[
  {
    "position": 1,
    "title": "Job title",
    "url": "https://...",
    "snippet": "Result summary",
    "domain": "company.com",
    "query": "site:linkedin.com/jobs \"front-end\" \"react\" \"remote\"",
    "query_index": 2,
    "page": 4,
    "page_position": 3
  }
]
```

`position` is global within the output file.

## Manual run (local)

Run the scraper manually in batch mode:

```bash
python3 erp_scraper.py --config data/queries/search_terms.json --results-dir data/results
```

Pagination defaults to 10 pages per query. You can override it:

```bash
python3 erp_scraper.py --config data/queries/search_terms.json --results-dir data/results --pages 10
```

Optional flags:

- `--pages` (default: `10`)
- `--results-per-page` (default: `30`)
- `--min-delay` (default: `2.0`)
- `--max-delay` (default: `6.0`)
- `--retries` (default: `4`)
- `--timeout` (default: `20`)

Single-query manual run is also available:

```bash
python3 erp_scraper.py --query "site:linkedin.com/jobs \"react\" \"remote\"" --out results/manual-run --pages 10
```

## Error behavior in batch mode

- If a query page returns no results, the scraper skips the remaining pages for that query and moves to the next query.
- If one query page fails (captcha/network), the scraper keeps processing remaining pages and queries.
- If one search term fails fatally, the scraper keeps processing the remaining search terms.
- A final summary is printed with success/failure totals.

## Manual run (GitHub Actions)

You can also trigger it manually in GitHub:

1. Open your repository on GitHub.
2. Go to `Actions`.
3. Open `Scrape Search Results`.
4. Click `Run workflow`.

## Tests

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

Current unit test coverage:

- Search-term schema validation for `queries` arrays.
- Pagination URL generation.
- Output path resolution from slug.
- Parser behavior for `snippet` and `domain`.

## GitHub Actions schedule

Workflow: `.github/workflows/scrape.yml`

- Runs daily at **06:00 UTC** (`0 6 * * *`).
- Also supports manual trigger via `workflow_dispatch`.
- Runs the scraper in batch mode.
- Creates an automatic PR only when `data/results/*.json` changes.
- Uses a unique branch per run (`auto/scrape-<timestamp>`).
