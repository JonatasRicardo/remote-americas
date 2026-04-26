#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import http.client
import json
import os
import random
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
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
DEFAULT_DOTENV_PATH = Path(".env")
DEFAULT_PAGES = 10
DEFAULT_RESULTS_PER_PAGE = 30
DEFAULT_JOB_TEXT_MAX_CHARS = 4000
OUTPUT_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SERPER_API_ENV = "SERPER_API_KEY"
SERPER_API_HOST = "google.serper.dev"
SERPER_SEARCH_PATH = "/search"
JSON_LD_SCRIPT_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
REQUIREMENTS_HEADING_KEYWORDS = (
    "requirements",
    "qualification",
    "what you'll need",
    "what you will need",
    "must have",
    "minimum qualifications",
    "basic qualifications",
    "required skills",
    "required experience",
)
DESCRIPTION_HEADING_KEYWORDS = (
    "job description",
    "about the role",
    "about this role",
    "role overview",
    "position overview",
    "what you'll do",
    "responsibilities",
)


class CaptchaDetected(Exception):
    pass


def load_dotenv(path: Path = DEFAULT_DOTENV_PATH) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key or key in os.environ:
            continue

        if value and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        os.environ[key] = value


def resolve_serper_api_key() -> str:
    api_key = os.environ.get(SERPER_API_ENV, "").strip()
    if api_key:
        return api_key

    raise ValueError(
        "Serper engine selected, but SERPER_API_KEY is missing. "
        "Set it in your shell or in a local .env file."
    )


def running_without_display_server() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


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

        launch_headless = not self.headed
        if self.headed and running_without_display_server():
            print("[WARN] --headed requested, but no display server was found. Falling back to headless mode.")
            launch_headless = True

        try:
            self._browser = self._playwright.chromium.launch(headless=launch_headless)
            self._context = self._browser.new_context(
                java_script_enabled=True,
                locale="en-US",
                user_agent=random.choice(UA_LIST),
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
        except Exception:
            # Ensure partially started Playwright state is fully stopped before retrying.
            try:
                self.close()
            except Exception:
                pass
            raise

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


def normalize_serper_batch_response(raw: Any, expected_items: int) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        maybe_results = raw.get("results")
        if isinstance(maybe_results, list):
            items = maybe_results
        else:
            items = [raw]
    else:
        raise ValueError("Serper API returned unexpected batch response format.")

    normalized: List[Dict[str, Any]] = [item if isinstance(item, dict) else {} for item in items]

    if len(normalized) < expected_items:
        normalized.extend({} for _ in range(expected_items - len(normalized)))
    elif len(normalized) > expected_items:
        normalized = normalized[:expected_items]

    return normalized


def fetch_serper_batch_payloads(
    batch_payload: List[Dict[str, Any]],
    cfg: Config,
    api_key: str,
) -> List[Dict[str, Any]]:
    payload = json.dumps(batch_payload)
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }

    for attempt in range(cfg.max_retries):
        connection = http.client.HTTPSConnection(SERPER_API_HOST, timeout=cfg.timeout)
        try:
            connection.request("POST", SERPER_SEARCH_PATH, payload, headers)
            response = connection.getresponse()
            raw_body = response.read().decode("utf-8", errors="ignore")

            if response.status >= 400:
                if response.status in (429, 503) and attempt < cfg.max_retries - 1:
                    wait = (cfg.backoff_base ** attempt) + random.uniform(0.3, 1.2)
                    time.sleep(wait)
                    continue
                raise ValueError(f"Serper API returned HTTP {response.status}: {raw_body[:200]}")

            try:
                data = json.loads(raw_body)
            except json.JSONDecodeError as exc:
                raise ValueError("Serper API returned invalid JSON response.") from exc

            return normalize_serper_batch_response(data, expected_items=len(batch_payload))
        except OSError:
            if attempt < cfg.max_retries - 1:
                wait = (cfg.backoff_base ** attempt) + random.uniform(0.3, 1.2)
                time.sleep(wait)
                continue
            raise
        finally:
            connection.close()

    raise RuntimeError("Failed to fetch results with Serper API after retries.")


def fetch_serper_results(
    query: str,
    cfg: Config,
    page: int,
    results_per_page: int,
    api_key: str,
) -> List[Dict[str, Any]]:
    batch_payload = [
        {
            "q": query,
            "page": page,
            "num": results_per_page,
        }
    ]
    batch_response = fetch_serper_batch_payloads(batch_payload=batch_payload, cfg=cfg, api_key=api_key)
    first_item = batch_response[0] if batch_response else {}
    return parse_serper_results(first_item)


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


def parse_serper_results(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    organic = raw.get("organic", [])
    if not isinstance(organic, list):
        return []

    results: List[Dict[str, Any]] = []
    for idx, item in enumerate(organic, start=1):
        if not isinstance(item, dict):
            continue

        title = str(item.get("title", "")).strip()
        url = str(item.get("link", "")).strip()
        snippet = str(item.get("snippet", "")).strip()

        raw_position = item.get("position", idx)
        try:
            page_position = int(raw_position)
        except (TypeError, ValueError):
            page_position = idx

        results.append(
            {
                "position": page_position,
                "title": title,
                "url": url,
                "snippet": snippet,
                "domain": extract_domain(url),
            }
        )

    return results


def normalize_space(value: str) -> str:
    return " ".join(value.split()).strip()


def is_jobposting_type(raw_type: Any) -> bool:
    if isinstance(raw_type, str):
        return raw_type.lower() == "jobposting"
    if isinstance(raw_type, list):
        return any(isinstance(item, str) and item.lower() == "jobposting" for item in raw_type)
    return False


def iter_json_objects(value: Any) -> Iterator[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from iter_json_objects(nested)
        return

    if isinstance(value, list):
        for item in value:
            yield from iter_json_objects(item)


def parse_json_ld_script(raw_script: str) -> Optional[Any]:
    payload = raw_script.strip()
    if not payload:
        return None

    if payload.startswith("<!--") and payload.endswith("-->"):
        payload = payload[4:-3].strip()
    if payload.startswith("<![CDATA[") and payload.endswith("]]>"):
        payload = payload[9:-3].strip()

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def find_jobposting_json_ld(html: str) -> Optional[Dict[str, Any]]:
    for match in JSON_LD_SCRIPT_RE.finditer(html):
        data = parse_json_ld_script(match.group(1))
        if data is None:
            continue

        for candidate in iter_json_objects(data):
            if is_jobposting_type(candidate.get("@type")):
                return candidate

    return None


def truncate_text(value: str, max_chars: int) -> str:
    if max_chars < 1:
        return ""
    if len(value) <= max_chars:
        return value

    truncated = value[: max_chars - 3].rstrip()
    return f"{truncated}..."


def html_to_visible_lines(html: str) -> List[str]:
    without_hidden_blocks = re.sub(
        r"(?is)<(script|style|noscript|svg|iframe)[^>]*>.*?</\1>",
        " ",
        html,
    )
    with_breaks = re.sub(r"(?i)<br\s*/?>", "\n", without_hidden_blocks)
    with_breaks = re.sub(
        r"(?i)</(p|div|li|section|article|h1|h2|h3|h4|h5|h6|ul|ol|tr|td|th|blockquote)>",
        "\n",
        with_breaks,
    )

    without_tags = re.sub(r"<[^>]+>", " ", with_breaks)
    text = unescape(without_tags)

    lines: List[str] = []
    for raw_line in text.splitlines():
        line = normalize_space(raw_line)
        if not line:
            continue
        if len(line) <= 1:
            continue
        lines.append(line)

    deduped_lines: List[str] = []
    previous = ""
    for line in lines:
        if line == previous:
            continue
        deduped_lines.append(line)
        previous = line

    return deduped_lines


def looks_like_heading(line: str) -> bool:
    normalized = line.strip()
    if not normalized:
        return False
    if len(normalized) > 120:
        return False

    if normalized.endswith(":"):
        return True

    lowered = normalized.lower()
    return any(keyword in lowered for keyword in DESCRIPTION_HEADING_KEYWORDS + REQUIREMENTS_HEADING_KEYWORDS)


def collect_lines_after_heading(lines: List[str], start_index: int, max_lines: int = 14) -> str:
    collected: List[str] = []
    for idx in range(start_index + 1, min(len(lines), start_index + 1 + max_lines)):
        line = lines[idx]
        if looks_like_heading(line) and collected:
            break
        if len(line) < 3:
            continue
        collected.append(line)

    return "\n".join(collected).strip()


def extract_section_by_heading(lines: List[str], heading_keywords: Tuple[str, ...]) -> str:
    for index, line in enumerate(lines):
        lowered = line.lower()
        if any(keyword in lowered for keyword in heading_keywords):
            section = collect_lines_after_heading(lines=lines, start_index=index)
            if section:
                return section
    return ""


def extract_meta_description(html: str) -> str:
    meta_tag_pattern = re.compile(r"<meta[^>]+>", re.I)
    for tag in meta_tag_pattern.findall(html):
        lower_tag = tag.lower()
        if (
            'name="description"' not in lower_tag
            and "name='description'" not in lower_tag
            and 'property="og:description"' not in lower_tag
            and "property='og:description'" not in lower_tag
            and 'name="twitter:description"' not in lower_tag
            and "name='twitter:description'" not in lower_tag
        ):
            continue

        match = re.search(r'content=(?:"([^"]*)"|\'([^\']*)\')', tag, re.I)
        if not match:
            continue
        content = match.group(1) or match.group(2) or ""
        content = normalize_space(unescape(content))
        if content:
            return content

    return ""


def collect_text_from_jobposting_field(raw: Any) -> str:
    if isinstance(raw, str):
        return clean_html_text(raw)
    if isinstance(raw, list):
        items = [collect_text_from_jobposting_field(item) for item in raw]
        merged = "\n".join(item for item in items if item)
        return merged.strip()
    if isinstance(raw, dict):
        if "name" in raw:
            name_text = collect_text_from_jobposting_field(raw.get("name"))
            if name_text:
                return name_text
        if "@value" in raw:
            value_text = collect_text_from_jobposting_field(raw.get("@value"))
            if value_text:
                return value_text
    return ""


def extract_description_and_requirements_from_html(html: str, max_chars: int) -> Tuple[str, str, str]:
    source_parts: List[str] = []
    description = ""
    requirements = ""

    jobposting = find_jobposting_json_ld(html)
    if jobposting:
        description = collect_text_from_jobposting_field(jobposting.get("description"))
        requirements = collect_text_from_jobposting_field(jobposting.get("qualifications"))
        if not requirements:
            requirement_chunks = [
                collect_text_from_jobposting_field(jobposting.get("experienceRequirements")),
                collect_text_from_jobposting_field(jobposting.get("educationRequirements")),
                collect_text_from_jobposting_field(jobposting.get("skills")),
            ]
            requirements = "\n".join(chunk for chunk in requirement_chunks if chunk).strip()

        source_parts.append("jsonld")

    lines = html_to_visible_lines(html)

    if not description:
        description = extract_section_by_heading(lines, DESCRIPTION_HEADING_KEYWORDS)
        if description:
            source_parts.append("html_heading_description")

    if not requirements:
        requirements = extract_section_by_heading(lines, REQUIREMENTS_HEADING_KEYWORDS)
        if requirements:
            source_parts.append("html_heading_requirements")

    if not description:
        description = extract_meta_description(html)
        if description:
            source_parts.append("meta_description")

    if not description and lines:
        fallback_lines = [line for line in lines if len(line) >= 60][:5]
        description = " ".join(fallback_lines).strip()
        if description:
            source_parts.append("text_fallback")

    if not requirements and lines:
        requirement_clues = ("required", "requirement", "qualification", "experience with", "must have", "proficient")
        requirement_lines = [line for line in lines if any(clue in line.lower() for clue in requirement_clues)]
        requirements = "\n".join(requirement_lines[:10]).strip()
        if requirements:
            source_parts.append("text_fallback")

    description = truncate_text(description, max_chars=max_chars)
    requirements = truncate_text(requirements, max_chars=max_chars)

    source = "none"
    if source_parts:
        source = ",".join(dict.fromkeys(source_parts))

    return description, requirements, source


def fetch_url_html(url: str, cfg: Config) -> Tuple[str, Optional[int], str]:
    for attempt in range(cfg.max_retries):
        headers = {
            "User-Agent": random.choice(UA_LIST),
            "Accept-Language": "en-US,en;q=0.9",
        }
        req = Request(url, headers=headers)

        try:
            with urlopen(req, timeout=cfg.timeout) as resp:
                content_type = resp.headers.get("Content-Type", "").lower()
                if "html" not in content_type and "xml" not in content_type:
                    raise ValueError(f"Unsupported content type: {content_type or 'unknown'}")

                raw_body = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                html = raw_body.decode(charset, errors="ignore")

                if looks_like_captcha(html):
                    raise CaptchaDetected("CAPTCHA detected while visiting result URL.")

                status = getattr(resp, "status", None)
                final_url = resp.geturl()
                return html, status, final_url

        except HTTPError as exc:
            if exc.code in (429, 503) and attempt < cfg.max_retries - 1:
                wait = (cfg.backoff_base ** attempt) + random.uniform(0.3, 1.2)
                time.sleep(wait)
                continue
            raise
        except (URLError, ValueError, OSError):
            if attempt < cfg.max_retries - 1:
                wait = (cfg.backoff_base ** attempt) + random.uniform(0.3, 1.2)
                time.sleep(wait)
                continue
            raise

    raise RuntimeError("Failed to fetch URL HTML after retries.")


def build_job_content_error_details(exc: Exception) -> Dict[str, Any]:
    status = None
    if isinstance(exc, HTTPError):
        status = exc.code

    return {
        "job_description": "",
        "job_requirements": "",
        "job_content_source": "none",
        "job_fetch_status": "error",
        "job_fetch_error": f"{type(exc).__name__}: {exc}",
        "job_fetch_http_status": status,
        "job_fetch_url": "",
    }


def enrich_rows_with_job_content(
    rows: List[Dict[str, Any]],
    cfg: Config,
    max_chars: int,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    per_url_cache: Dict[str, Dict[str, Any]] = {}
    unique_urls = [str(row.get("url", "")).strip() for row in rows if str(row.get("url", "")).strip()]
    total_unique_urls = len(set(unique_urls))
    processed_unique_urls = 0

    for row_index, row in enumerate(rows, start=1):
        url = str(row.get("url", "")).strip()
        if not url:
            row.update(
                {
                    "job_description": "",
                    "job_requirements": "",
                    "job_content_source": "none",
                    "job_fetch_status": "skipped",
                    "job_fetch_error": "missing url",
                    "job_fetch_http_status": None,
                    "job_fetch_url": "",
                }
            )
            continue

        cached = per_url_cache.get(url)
        if cached is not None:
            row.update(dict(cached))
            continue

        processed_unique_urls += 1
        print(f"[INFO] Enriching URL {processed_unique_urls}/{total_unique_urls}: {url}")

        try:
            html, http_status, final_url = fetch_url_html(url=url, cfg=cfg)
            description, requirements, source = extract_description_and_requirements_from_html(
                html=html,
                max_chars=max_chars,
            )
            fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

            details = {
                "job_description": description,
                "job_requirements": requirements,
                "job_content_source": source,
                "job_fetch_status": "ok" if description or requirements else "empty",
                "job_fetch_error": "",
                "job_fetch_http_status": http_status,
                "job_fetch_url": final_url,
                "job_fetched_at_utc": fetched_at,
            }
        except Exception as exc:  # noqa: BLE001
            details = build_job_content_error_details(exc)
            msg = f"row={row_index}, url={url}: {type(exc).__name__}: {exc}"
            errors.append(msg)
            print(f"[WARN] URL enrichment failed: {msg}")

        per_url_cache[url] = details
        row.update(dict(details))

        should_sleep = processed_unique_urls < total_unique_urls
        sleep_between_requests(cfg, should_sleep=should_sleep)

    return rows, errors


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


def collect_results_for_queries_serper(
    queries: List[str],
    cfg: Config,
    pages: int,
    results_per_page: int,
    api_key: str,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    global_position = 1

    for query_index, query in enumerate(queries, start=1):
        batch_payload = [
            {
                "q": query,
                "page": page,
                "num": results_per_page,
            }
            for page in range(1, pages + 1)
        ]
        should_sleep = query_index != len(queries)

        try:
            batch_pages = fetch_serper_batch_payloads(batch_payload=batch_payload, cfg=cfg, api_key=api_key)
        except Exception as exc:  # noqa: BLE001
            msg = f"query_index={query_index}, page=batch: {type(exc).__name__}: {exc}"
            errors.append(msg)
            print(f"[WARN] Query batch failed: {msg}")
            sleep_between_requests(cfg, should_sleep=should_sleep)
            continue

        for page, raw_page in enumerate(batch_pages, start=1):
            print(f"[INFO] Query {query_index}/{len(queries)} | Page {page}/{pages}: {query}")
            page_rows = parse_serper_results(raw_page)

            if not page_rows:
                print(f"[INFO] No results on page {page} for query index {query_index}.")
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
    extract_job_details: bool = False,
    job_text_max_chars: int = DEFAULT_JOB_TEXT_MAX_CHARS,
) -> int:
    if engine == "serper":
        api_key = resolve_serper_api_key()
        rows, errors = collect_results_for_queries_serper(
            queries=[query],
            cfg=cfg,
            pages=pages,
            results_per_page=results_per_page,
            api_key=api_key,
        )
    else:
        with resolve_fetcher(engine=engine, headed=headed) as fetch_html:
            rows, errors = collect_results_for_queries(
                queries=[query],
                cfg=cfg,
                pages=pages,
                results_per_page=results_per_page,
                fetch_html=fetch_html,
            )

    if extract_job_details:
        rows, enrich_errors = enrich_rows_with_job_content(rows=rows, cfg=cfg, max_chars=job_text_max_chars)
        errors.extend(enrich_errors)

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
    extract_job_details: bool = False,
    job_text_max_chars: int = DEFAULT_JOB_TEXT_MAX_CHARS,
) -> int:
    terms = load_search_terms(config_path)
    print(f"[INFO] Loaded search terms: {len(terms)}")

    success_count = 0
    failed_count = 0
    page_error_count = 0
    failure_messages: List[str] = []

    if engine == "serper":
        api_key = resolve_serper_api_key()
        for term in terms:
            output_path = resolve_output_path(term.output, results_dir)
            print(f"\n[RUN] {term.title} -> {output_path}")
            print(f"[INFO] Queries: {len(term.queries)} | Pages per query: {pages}")

            try:
                rows, page_errors = collect_results_for_queries_serper(
                    queries=term.queries,
                    cfg=cfg,
                    pages=pages,
                    results_per_page=results_per_page,
                    api_key=api_key,
                )
                all_errors = list(page_errors)
                if extract_job_details:
                    rows, enrich_errors = enrich_rows_with_job_content(rows=rows, cfg=cfg, max_chars=job_text_max_chars)
                    all_errors.extend(enrich_errors)
                save_json(rows, output_path)

                page_error_count += len(all_errors)
                success_count += 1

                print(f"[OK] Saved {len(rows)} rows to {output_path}")
                if all_errors:
                    print(f"[WARN] {len(all_errors)} request(s) failed while processing '{term.title}'.")
                    for page_error in all_errors:
                        print(f" - {page_error}")

            except Exception as exc:  # noqa: BLE001
                failed_count += 1
                message = f"{term.output}: {type(exc).__name__}: {exc}"
                failure_messages.append(message)
                print(f"[WARN] Search term failed for '{term.title}': {type(exc).__name__}: {exc}")
    else:
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
                    all_errors = list(page_errors)
                    if extract_job_details:
                        rows, enrich_errors = enrich_rows_with_job_content(
                            rows=rows,
                            cfg=cfg,
                            max_chars=job_text_max_chars,
                        )
                        all_errors.extend(enrich_errors)
                    save_json(rows, output_path)

                    page_error_count += len(all_errors)
                    success_count += 1

                    print(f"[OK] Saved {len(rows)} rows to {output_path}")
                    if all_errors:
                        print(f"[WARN] {len(all_errors)} request(s) failed while processing '{term.title}'.")
                        for page_error in all_errors:
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
    load_dotenv()

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
        choices=("http", "playwright", "serper"),
        default="http",
        help=(
            "Fetcher engine: 'http' (default), 'playwright' for real Chromium browser with JavaScript, "
            "or 'serper' for Google SERP API via SERPER_API_KEY."
        ),
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Open visible Chromium window (only used with --engine playwright).",
    )
    parser.add_argument(
        "--extract-job-details",
        action="store_true",
        help="Visit each result URL and extract job description/requirements from the page HTML.",
    )
    parser.add_argument(
        "--job-max-chars",
        type=int,
        default=DEFAULT_JOB_TEXT_MAX_CHARS,
        help=f"Maximum characters per extracted job text field (default: {DEFAULT_JOB_TEXT_MAX_CHARS}).",
    )

    args = parser.parse_args()

    if args.query and args.config:
        parser.error("Use only one mode at a time: --query or --config.")

    if args.pages < 1:
        parser.error("--pages must be >= 1.")

    if args.results_per_page < 1:
        parser.error("--results-per-page must be >= 1.")
    if args.job_max_chars < 1:
        parser.error("--job-max-chars must be >= 1.")

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
                extract_job_details=args.extract_job_details,
                job_text_max_chars=args.job_max_chars,
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
            extract_job_details=args.extract_job_details,
            job_text_max_chars=args.job_max_chars,
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
