#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import erp_scraper

DEFAULT_CONFIG_PATH = Path("data/queries/search_terms.json")
DEFAULT_RESULTS_DIR = Path("data/results")
DEFAULT_BATCH_SIZE = 20


def load_rows(path: Path) -> List[Dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Result JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(raw, list):
        raise ValueError(f"Result file must be a JSON array: {path}")

    rows: List[Dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Result row {index} in {path} must be an object.")
        rows.append(item)

    return rows


def resolve_result_paths(config_path: Path, results_dir: Path) -> List[Path]:
    terms = erp_scraper.load_search_terms(config_path)
    return [erp_scraper.resolve_output_path(term.output, results_dir) for term in terms]


def iter_batches(items: List[str], batch_size: int) -> Iterable[List[str]]:
    for index in range(0, len(items), batch_size):
        yield items[index : index + batch_size]


def _build_success_details(
    *,
    description: str,
    requirements: str,
    source: str,
    http_status: Optional[int],
    final_url: str,
) -> Dict[str, Any]:
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "job_description": description,
        "job_requirements": requirements,
        "job_content_source": source,
        "job_fetch_status": "ok" if description or requirements else "empty",
        "job_fetch_error": "",
        "job_fetch_http_status": http_status,
        "job_fetch_url": final_url,
        "job_fetched_at_utc": fetched_at,
    }


def _build_missing_url_details() -> Dict[str, Any]:
    return {
        "job_description": "",
        "job_requirements": "",
        "job_content_source": "none",
        "job_fetch_status": "skipped",
        "job_fetch_error": "missing url",
        "job_fetch_http_status": None,
        "job_fetch_url": "",
    }


def _process_url_sync(url: str, cfg: erp_scraper.Config, max_chars: int) -> Tuple[Dict[str, Any], Optional[str]]:
    try:
        html, http_status, final_url = erp_scraper.fetch_url_html(url=url, cfg=cfg)
        description, requirements, source = erp_scraper.extract_description_and_requirements_from_html(
            html=html,
            max_chars=max_chars,
        )
        return (
            _build_success_details(
                description=description,
                requirements=requirements,
                source=source,
                http_status=http_status,
                final_url=final_url,
            ),
            None,
        )
    except Exception as exc:  # noqa: BLE001
        details = erp_scraper.build_job_content_error_details(exc)
        error = f"url={url}: {type(exc).__name__}: {exc}"
        return details, error


async def _run_batch(
    *,
    batch_urls: List[str],
    cfg: erp_scraper.Config,
    max_chars: int,
    executor: ThreadPoolExecutor,
) -> List[Tuple[str, Dict[str, Any], Optional[str]]]:
    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(executor, _process_url_sync, url, cfg, max_chars)
        for url in batch_urls
    ]
    results = await asyncio.gather(*tasks)
    return [(url, details, error) for url, (details, error) in zip(batch_urls, results)]


async def _enrich_unique_urls_async(
    *,
    unique_urls: List[str],
    cfg: erp_scraper.Config,
    max_chars: int,
    batch_size: int,
    executor: ThreadPoolExecutor,
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    per_url_cache: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    total_batches = (len(unique_urls) + batch_size - 1) // batch_size

    for batch_index, batch_urls in enumerate(iter_batches(unique_urls, batch_size), start=1):
        print(
            f"[INFO] Processing URL batch {batch_index}/{total_batches} "
            f"({len(batch_urls)} URL(s), size={batch_size})"
        )
        batch_results = await _run_batch(
            batch_urls=batch_urls,
            cfg=cfg,
            max_chars=max_chars,
            executor=executor,
        )

        for url, details, error in batch_results:
            per_url_cache[url] = details
            if error:
                errors.append(error)
                print(f"[WARN] URL enrichment failed: {error}")

        if batch_index < total_batches and cfg.max_delay > 0:
            delay = random.uniform(cfg.min_delay, cfg.max_delay)
            print(f"[INFO] Sleeping {delay:.2f}s before next batch")
            await asyncio.sleep(delay)

    return per_url_cache, errors


def enrich_rows_with_job_content_batched(
    rows: List[Dict[str, Any]],
    cfg: erp_scraper.Config,
    max_chars: int,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    unique_urls: List[str] = []
    seen_urls = set()
    for row in rows:
        url = str(row.get("url", "")).strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        unique_urls.append(url)

    if unique_urls:
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            per_url_cache, errors = asyncio.run(
                _enrich_unique_urls_async(
                    unique_urls=unique_urls,
                    cfg=cfg,
                    max_chars=max_chars,
                    batch_size=batch_size,
                    executor=executor,
                )
            )
    else:
        per_url_cache = {}
        errors = []

    for row in rows:
        url = str(row.get("url", "")).strip()
        if not url:
            row.update(_build_missing_url_details())
            continue

        details = per_url_cache.get(url)
        if details is None:
            # Defensive fallback in case a URL was not processed for any reason.
            details = {
                **_build_missing_url_details(),
                "job_fetch_status": "error",
                "job_fetch_error": "url not processed",
            }
        row.update(dict(details))

    return rows, errors


def enrich_result_file(
    path: Path,
    cfg: erp_scraper.Config,
    max_chars: int,
    batch_size: int,
) -> Tuple[int, int]:
    rows = load_rows(path)
    if not rows:
        print(f"[INFO] Empty result file. Skipping enrichment: {path}")
        return 0, 0

    enriched_rows, errors = enrich_rows_with_job_content_batched(
        rows=rows,
        cfg=cfg,
        max_chars=max_chars,
        batch_size=batch_size,
    )
    erp_scraper.save_json(enriched_rows, path)

    print(f"[OK] Enriched {len(enriched_rows)} rows in {path}")
    if errors:
        print(f"[WARN] {len(errors)} request(s) failed while enriching {path.name}.")
        for err in errors:
            print(f" - {err}")

    return len(enriched_rows), len(errors)


def run_batch(
    config_path: Path,
    results_dir: Path,
    cfg: erp_scraper.Config,
    max_chars: int,
    batch_size: int,
) -> int:
    paths = resolve_result_paths(config_path=config_path, results_dir=results_dir)
    print(f"[INFO] Files to enrich from config: {len(paths)}")

    enriched_files = 0
    failed_files = 0
    total_rows = 0
    total_errors = 0

    for path in paths:
        print(f"\n[RUN] Enriching: {path}")
        if not path.exists():
            print(f"[WARN] Result file does not exist yet. Skipping: {path}")
            failed_files += 1
            continue

        try:
            row_count, error_count = enrich_result_file(path=path, cfg=cfg, max_chars=max_chars, batch_size=batch_size)
            total_rows += row_count
            total_errors += error_count
            enriched_files += 1
        except Exception as exc:  # noqa: BLE001
            failed_files += 1
            print(f"[WARN] Failed to enrich {path}: {type(exc).__name__}: {exc}")

    print("\n[SUMMARY]")
    print(f"[SUMMARY] Files enriched: {enriched_files}")
    print(f"[SUMMARY] Files failed:   {failed_files}")
    print(f"[SUMMARY] Rows processed: {total_rows}")
    print(f"[SUMMARY] URL failures:   {total_errors}")
    return 0


def run_single_file(path: Path, cfg: erp_scraper.Config, max_chars: int, batch_size: int) -> int:
    row_count, error_count = enrich_result_file(path=path, cfg=cfg, max_chars=max_chars, batch_size=batch_size)
    print("\n[SUMMARY]")
    print(f"[SUMMARY] Rows processed: {row_count}")
    print(f"[SUMMARY] URL failures:   {error_count}")
    return 0


def main() -> int:
    erp_scraper.load_dotenv()

    parser = argparse.ArgumentParser(
        description=(
            "Second-stage routine: read result JSON files, visit each URL directly, and enrich "
            "rows with job description and requirements extracted from HTML."
        )
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"JSON config file used to locate result files (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--results-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help=f"Result directory where output JSON files are stored (default: {DEFAULT_RESULTS_DIR})",
    )
    parser.add_argument(
        "--file",
        help="Optional single JSON result file to enrich. If set, --config/--results-dir are ignored.",
    )
    parser.add_argument("--min-delay", type=float, default=2.0)
    parser.add_argument("--max-delay", type=float, default=6.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Number of URLs processed concurrently per batch (default: {DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--job-max-chars",
        type=int,
        default=erp_scraper.DEFAULT_JOB_TEXT_MAX_CHARS,
        help=f"Maximum characters per extracted text field (default: {erp_scraper.DEFAULT_JOB_TEXT_MAX_CHARS}).",
    )

    args = parser.parse_args()

    if args.job_max_chars < 1:
        parser.error("--job-max-chars must be >= 1.")
    if args.min_delay < 0 or args.max_delay < 0:
        parser.error("--min-delay and --max-delay must be >= 0.")
    if args.max_delay < args.min_delay:
        parser.error("--max-delay must be >= --min-delay.")
    if args.retries < 1:
        parser.error("--retries must be >= 1.")
    if args.timeout < 1:
        parser.error("--timeout must be >= 1.")
    if args.batch_size < 1:
        parser.error("--batch-size must be >= 1.")

    cfg = erp_scraper.Config(
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        max_retries=args.retries,
        timeout=args.timeout,
    )

    try:
        if args.file:
            return run_single_file(
                path=Path(args.file),
                cfg=cfg,
                max_chars=args.job_max_chars,
                batch_size=args.batch_size,
            )

        return run_batch(
            config_path=Path(args.config),
            results_dir=Path(args.results_dir),
            cfg=cfg,
            max_chars=args.job_max_chars,
            batch_size=args.batch_size,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
