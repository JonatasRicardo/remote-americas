#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import random
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


@dataclass
class Config:
    min_delay: float = 2.0
    max_delay: float = 6.0
    max_retries: int = 4
    backoff_base: float = 1.8
    timeout: int = 20


@dataclass
class SearchTerm:
    title: str
    queries: List[str]
    output: str


UA_LIST = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
]

DEFAULT_CONFIG_PATH = Path("data/queries/search_terms.json")
DEFAULT_RESULTS_DIR = Path("data/results")
DEFAULT_PAGES = 10
DEFAULT_RESULTS_PER_PAGE = 30
OUTPUT_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class CaptchaDetected(Exception):
    pass


class PlaywrightFetcher:
    """
    Lazy Playwright-backed fetcher that reuses one browser context.
    """

    def __init__(self, headed: bool = False):
        self.headed = headed
        self._playwright = None
        self._browser = None
        self._context = None
        self._timeout_error_cls = None

    def _ensure_started(self) -> None:
        if self._context is not None:
            return

        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ValueError(
                "Playwright engine selected, but dependency is missing. "
                "Install with: pip install playwright && python -m playwright install chromium"
            ) from exc

        self._timeout_error_cls = PlaywrightTimeoutError
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=not self.headed)
        self._context = self._browser.new_context(
            java_script_enabled=True,
            locale="en-US",
            user_agent=random.choice(UA_LIST),
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )

    def fetch_ddg_html(self, query: str, cfg: "Config", page: int, results_per_page: int) -> str:
        self._ensure_started()
        assert self._context is not None
        assert self._timeout_error_cls is not None

        url = build_ddh_url(query=query, page=page, results_per_page=results_per_page)

        for attempt in range(cfg.max_retries):
            page_obj = self._context.new_page()
            try:
                page_obj.set_default_timeout(cfg.timeout * 1000)
                page_obj.goto(url, wait_until="domcontentloaded")
                html = page_obj.content()

                if looks_like_captcha(html):
                    raise CaptchaDetected("CAPTCHA detected. Stopping to avoid anti-bot policy violations.")

                return html

            except self._timeout_error_cls:
                if attempt < cfg.max_retries - 1:
                    wait = (cfg.backoff_base ** attempt) + random.uniform(0.3, 1.2)
                    time.sleep(wait)
                    continue
                raise
            except Exception:
                if attempt < cfg.max_retries - 1:
                    wait = (cfg.backoff_base ** attempt) + random.uniform(0.3, 1.2)
                    time.sleep(wait)
                    continue
                raise
            finally:
                page_obj.close()

        raise RuntimeError("Failed to fetch HTML with Playwright after retries.")

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None


FetchHtmlFn = Callable[[str, "Config", int, int], str]


@contextmanager
def resolve_fetcher(engine: str, headed: bool = False) -> Iterator[FetchHtmlFn]:
    if engine == "http":
        yield fetch_ddg_html
        return

    if engine == "playwright":
        fetcher = PlaywrightFetcher(headed=headed)
        try:
            yield fetcher.fetch_ddg_html
        finally:
            fetcher.close()
        return

    raise ValueError(f"Unknown engine '{engine}'. Use 'http' or 'playwright'.")


def looks_like_captcha(html: str) -> bool:
    signals = [
        "recaptcha",
        "g-recaptcha",
        "detected unusual traffic",
        "prove you are human",
        "/sorry/index",
        "captcha",
    ]
    low = html.lower()
    return any(signal in low for signal in signals)


def build_ddh_url(query: str, page: int = 1, results_per_page: int = DEFAULT_RESULTS_PER_PAGE) -> str:
    base = "https://duckduckgo.com/html/"
    normalized_query = query.replace("site:https://", "site:").replace("site:http://", "site:")
    params: Dict[str, Any] = {"q": normalized_query}

    if page > 1:
        offset = (page - 1) * results_per_page
        params["s"] = offset

    return f"{base}?{urlencode(params)}"


def fetch_ddg_html(query: str, cfg: Config, page: int, results_per_page: int) -> str:
    """
    Fetches one DuckDuckGo result page for the given query.
    """
    url = build_ddh_url(query=query, page=page, results_per_page=results_per_page)

    for attempt in range(cfg.max_retries):
        headers = {
            "User-Agent": random.choice(UA_LIST),
            "Accept-Language": "en-US,en;q=0.9",
        }
        req = Request(url, headers=headers)

        try:
            with urlopen(req, timeout=cfg.timeout) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            if looks_like_captcha(html):
                raise CaptchaDetected("CAPTCHA detected. Stopping to avoid anti-bot policy violations.")

            return html

        except HTTPError as exc:
            # 429/503 are common for temporary rate limiting.
            if exc.code in (429, 503) and attempt < cfg.max_retries - 1:
                wait = (cfg.backoff_base ** attempt) + random.uniform(0.3, 1.2)
                time.sleep(wait)
                continue
            raise
        except URLError:
            if attempt < cfg.max_retries - 1:
                wait = (cfg.backoff_base ** attempt) + random.uniform(0.3, 1.2)
                time.sleep(wait)
                continue
            raise


def clean_html_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", "", value)
    normalized_ws = " ".join(unescape(without_tags).split())
    return normalized_ws.strip()


def normalize_result_url(href: str) -> str:
    href = href.strip()
    if not href:
        return href

    if href.startswith("//"):
        href = f"https:{href}"
    elif href.startswith("/"):
        href = urljoin("https://duckduckgo.com", href)

    parsed = urlparse(href)
    netloc = parsed.netloc.lower()

    if "duckduckgo.com" in netloc and parsed.path.startswith("/l/"):
        qs = parse_qs(parsed.query)
        uddg = qs.get("uddg", [""])[0]
        if uddg:
            return uddg

    return href


def extract_domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""

    if host.startswith("www."):
        host = host[4:]
    return host


def parse_ddg_results(html: str) -> List[Dict[str, Any]]:
    """
    Lightweight regex-based parser for DuckDuckGo result blocks.
    """
    title_pattern = re.compile(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.I | re.S,
    )
    snippet_pattern = re.compile(
        r'<(?:a|div|span)[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|div|span)>',
        re.I | re.S,
    )

    snippets = [clean_html_text(match.group(1)) for match in snippet_pattern.finditer(html)]

    results: List[Dict[str, Any]] = []
    for idx, match in enumerate(title_pattern.finditer(html), start=1):
        raw_href = match.group(1)
        normalized_url = normalize_result_url(raw_href)
        title = clean_html_text(match.group(2))
        snippet = snippets[idx - 1] if idx - 1 < len(snippets) else ""

        results.append(
            {
                "position": idx,
                "title": title,
                "url": normalized_url,
                "snippet": snippet,
                "domain": extract_domain(normalized_url),
            }
        )
    return results


def save_json(rows: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_obj:
        json.dump(rows, file_obj, ensure_ascii=False, indent=2)


def validate_search_terms(raw: Any) -> List[SearchTerm]:
    if not isinstance(raw, list):
        raise ValueError("Config JSON must be an array of objects.")

    terms: List[SearchTerm] = []
    outputs_seen = set()

    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Item {idx}: expected a JSON object.")

        for field in ("title", "queries", "output"):
            if field not in item:
                raise ValueError(f"Item {idx}: missing required field '{field}'.")

        if not isinstance(item["title"], str) or not item["title"].strip():
            raise ValueError(f"Item {idx}: field 'title' must be a non-empty string.")
        if not isinstance(item["output"], str) or not item["output"].strip():
            raise ValueError(f"Item {idx}: field 'output' must be a non-empty string.")
        if not isinstance(item["queries"], list) or not item["queries"]:
            raise ValueError(f"Item {idx}: field 'queries' must be a non-empty array of strings.")

        queries: List[str] = []
        for q_idx, query in enumerate(item["queries"], start=1):
            if not isinstance(query, str) or not query.strip():
                raise ValueError(f"Item {idx}, query {q_idx}: each query must be a non-empty string.")
            queries.append(query.strip())

        output = item["output"].strip()
        if not OUTPUT_SLUG_RE.fullmatch(output):
            raise ValueError(
                f"Item {idx}: invalid output '{output}'. Use lowercase kebab-case (e.g. frontend-react-remote)."
            )
        if output in outputs_seen:
            raise ValueError(f"Item {idx}: duplicate output '{output}'.")

        outputs_seen.add(output)
        terms.append(
            SearchTerm(
                title=item["title"].strip(),
                queries=queries,
                output=output,
            )
        )

    if not terms:
        raise ValueError("Config JSON cannot be empty.")

    return terms


def load_search_terms(config_path: Path) -> List[SearchTerm]:
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Config file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {config_path}: {exc}") from exc

    return validate_search_terms(raw)


def resolve_output_path(output_slug: str, results_dir: Path = DEFAULT_RESULTS_DIR) -> Path:
    return results_dir / f"{output_slug}.json"


def sleep_between_requests(cfg: Config, should_sleep: bool) -> None:
    if not should_sleep:
        return

    delay = random.uniform(cfg.min_delay, cfg.max_delay)
    print(f"[INFO] Sleeping {delay:.2f}s")
    time.sleep(delay)


def collect_results_for_queries(
    queries: List[str],
    cfg: Config,
    pages: int,
    results_per_page: int,
    fetch_html: Optional[FetchHtmlFn] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    if fetch_html is None:
        fetch_html = fetch_ddg_html

    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    global_position = 1

    for query_index, query in enumerate(queries, start=1):
        for page in range(1, pages + 1):
            print(f"[INFO] Query {query_index}/{len(queries)} | Page {page}/{pages}: {query}")
            should_sleep = not (query_index == len(queries) and page == pages)

            try:
                html = fetch_html(query=query, cfg=cfg, page=page, results_per_page=results_per_page)
                page_rows = parse_ddg_results(html)

                if not page_rows:
                    print(f"[INFO] No results on page {page} for query index {query_index}.")
                    print(html)
                    break

                for page_position, base_row in enumerate(page_rows, start=1):
                    row = dict(base_row)
                    row["position"] = global_position
                    row["query"] = query
                    row["query_index"] = query_index
                    row["page"] = page
                    row["page_position"] = page_position
                    rows.append(row)
                    global_position += 1

            except Exception as exc:  # noqa: BLE001
                msg = f"query_index={query_index}, page={page}: {type(exc).__name__}: {exc}"
                errors.append(msg)
                print(f"[WARN] Page failed: {msg}")
            finally:
                sleep_between_requests(cfg, should_sleep=should_sleep)

    return rows, errors


def run_single_query(
    query: str,
    output_path: Path,
    cfg: Config,
    pages: int,
    results_per_page: int,
    engine: str = "http",
    headed: bool = False,
) -> int:
    with resolve_fetcher(engine=engine, headed=headed) as fetch_html:
        rows, errors = collect_results_for_queries(
            queries=[query],
            cfg=cfg,
            pages=pages,
            results_per_page=results_per_page,
            fetch_html=fetch_html,
        )
    save_json(rows, output_path)

    print(f"[OK] Results: {len(rows)}")
    print(f"[OK] JSON: {output_path}")
    if errors:
        print("[SUMMARY] Errors in single-run mode:")
        for error in errors:
            print(f" - {error}")
    return len(rows)


def run_batch(
    config_path: Path,
    results_dir: Path,
    cfg: Config,
    pages: int,
    results_per_page: int,
    engine: str = "http",
    headed: bool = False,
) -> int:
    terms = load_search_terms(config_path)
    print(f"[INFO] Loaded search terms: {len(terms)}")

    success_count = 0
    failed_count = 0
    page_error_count = 0
    failure_messages: List[str] = []

    with resolve_fetcher(engine=engine, headed=headed) as fetch_html:
        for term in terms:
            output_path = resolve_output_path(term.output, results_dir)
            print(f"\n[RUN] {term.title} -> {output_path}")
            print(f"[INFO] Queries: {len(term.queries)} | Pages per query: {pages}")

            try:
                rows, page_errors = collect_results_for_queries(
                    queries=term.queries,
                    cfg=cfg,
                    pages=pages,
                    results_per_page=results_per_page,
                    fetch_html=fetch_html,
                )
                save_json(rows, output_path)

                page_error_count += len(page_errors)
                success_count += 1

                print(f"[OK] Saved {len(rows)} rows to {output_path}")
                if page_errors:
                    print(f"[WARN] {len(page_errors)} page(s) failed while processing '{term.title}'.")
                    for page_error in page_errors:
                        print(f" - {page_error}")

            except Exception as exc:  # noqa: BLE001
                failed_count += 1
                message = f"{term.output}: {type(exc).__name__}: {exc}"
                failure_messages.append(message)
                print(f"[WARN] Search term failed for '{term.title}': {type(exc).__name__}: {exc}")

    print("\n[SUMMARY]")
    print(f"[SUMMARY] Search terms succeeded: {success_count}")
    print(f"[SUMMARY] Search terms failed:    {failed_count}")
    print(f"[SUMMARY] Page-level failures:    {page_error_count}")
    if failure_messages:
        print("[SUMMARY] Fatal term errors:")
        for message in failure_messages:
            print(f" - {message}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Simple compliance-first SERP scraper.")
    parser.add_argument("--query", help="Search query for single-run mode")
    parser.add_argument("--out", default="results", help="Output prefix for single-run mode")
    parser.add_argument(
        "--config",
        help=f"JSON config file for batch mode (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR), help="Output directory for batch mode")
    parser.add_argument("--pages", type=int, default=DEFAULT_PAGES, help="Pages to fetch per query (default: 10)")
    parser.add_argument(
        "--results-per-page",
        type=int,
        default=DEFAULT_RESULTS_PER_PAGE,
        help="Estimated results per page for pagination offsets",
    )
    parser.add_argument("--min-delay", type=float, default=2.0)
    parser.add_argument("--max-delay", type=float, default=6.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument(
        "--engine",
        choices=("http", "playwright"),
        default="http",
        help="Fetcher engine: 'http' (default) or 'playwright' for real Chromium browser with JavaScript.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Open visible Chromium window (only used with --engine playwright).",
    )

    args = parser.parse_args()

    if args.query and args.config:
        parser.error("Use only one mode at a time: --query or --config.")

    if args.pages < 1:
        parser.error("--pages must be >= 1.")

    if args.results_per_page < 1:
        parser.error("--results-per-page must be >= 1.")

    if args.headed and args.engine != "playwright":
        print("[WARN] --headed has no effect unless --engine playwright.")

    if not args.query and not args.config:
        args.config = str(DEFAULT_CONFIG_PATH)

    cfg = Config(
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        max_retries=args.retries,
        timeout=args.timeout,
    )

    try:
        if args.query:
            output_path = Path(f"{args.out}.json")
            run_single_query(
                query=args.query,
                output_path=output_path,
                cfg=cfg,
                pages=args.pages,
                results_per_page=args.results_per_page,
                engine=args.engine,
                headed=args.headed,
            )
            return 0

        config_path = Path(args.config)
        results_dir = Path(args.results_dir)
        return run_batch(
            config_path=config_path,
            results_dir=results_dir,
            cfg=cfg,
            pages=args.pages,
            results_per_page=args.results_per_page,
            engine=args.engine,
            headed=args.headed,
        )
    except CaptchaDetected as exc:
        print(f"[STOP] {exc}")
        print("[TIP] For production reliability, prefer a SERP API.")
        return 1
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
