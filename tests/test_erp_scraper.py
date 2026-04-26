import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

import erp_scraper


class ValidateSearchTermsTests(unittest.TestCase):
    def test_validate_accepts_valid_list(self):
        raw = [
            {
                "title": "Frontend Remote",
                "queries": [
                    "site:greenhouse.com \"frontend\" \"remote\"",
                    "site:linkedin.com/jobs \"frontend\" \"remote\"",
                ],
                "output": "frontend-remote",
            }
        ]

        terms = erp_scraper.validate_search_terms(raw)

        self.assertEqual(1, len(terms))
        self.assertEqual("frontend-remote", terms[0].output)
        self.assertEqual(2, len(terms[0].queries))

    def test_validate_rejects_missing_queries_field(self):
        raw = [{"title": "Frontend", "output": "frontend-remote"}]

        with self.assertRaises(ValueError) as ctx:
            erp_scraper.validate_search_terms(raw)

        self.assertIn("missing required field 'queries'", str(ctx.exception))

    def test_validate_rejects_empty_queries_array(self):
        raw = [{"title": "Frontend", "queries": [], "output": "frontend-remote"}]

        with self.assertRaises(ValueError) as ctx:
            erp_scraper.validate_search_terms(raw)

        self.assertIn("non-empty array", str(ctx.exception))

    def test_validate_rejects_invalid_slug(self):
        raw = [
            {
                "title": "Frontend",
                "queries": ["site:greenhouse.com \"frontend\" \"remote\""],
                "output": "Frontend Remote",
            }
        ]

        with self.assertRaises(ValueError) as ctx:
            erp_scraper.validate_search_terms(raw)

        self.assertIn("invalid output", str(ctx.exception))


class PaginationUrlTests(unittest.TestCase):
    def test_build_url_first_page_has_no_offset(self):
        url = erp_scraper.build_ddh_url("site:https://greenhouse.com remote", page=1, results_per_page=30)
        qs = parse_qs(urlparse(url).query)

        self.assertEqual("site:greenhouse.com remote", qs["q"][0])
        self.assertNotIn("s", qs)

    def test_build_url_second_page_has_offset(self):
        url = erp_scraper.build_ddh_url("site:linkedin.com/jobs remote", page=3, results_per_page=30)
        qs = parse_qs(urlparse(url).query)

        self.assertEqual("60", qs["s"][0])


class QueryPaginationBehaviorTests(unittest.TestCase):
    def test_empty_page_skips_to_next_query(self):
        cfg = erp_scraper.Config(min_delay=0, max_delay=0, max_retries=1, timeout=1)
        queries = ["query-one", "query-two"]

        def fake_parse(html: str):
            if html == "query-one|1":
                return [
                    {
                        "position": 1,
                        "title": "One",
                        "url": "https://example.com/one",
                        "snippet": "snippet one",
                        "domain": "example.com",
                    }
                ]
            if html == "query-one|2":
                return []
            if html == "query-two|1":
                return [
                    {
                        "position": 1,
                        "title": "Two",
                        "url": "https://example.com/two",
                        "snippet": "snippet two",
                        "domain": "example.com",
                    }
                ]
            if html == "query-two|2":
                return []
            raise AssertionError(f"Unexpected html marker: {html}")

        with mock.patch(
            "erp_scraper.fetch_ddg_html",
            side_effect=lambda query, cfg, page, results_per_page: f"{query}|{page}",
        ) as fetch_mock, mock.patch(
            "erp_scraper.parse_ddg_results",
            side_effect=fake_parse,
        ), mock.patch(
            "erp_scraper.sleep_between_requests",
            return_value=None,
        ):
            rows, errors = erp_scraper.collect_results_for_queries(
                queries=queries,
                cfg=cfg,
                pages=3,
                results_per_page=30,
            )

        self.assertEqual([], errors)
        self.assertEqual(2, len(rows))

        self.assertEqual("query-one", rows[0]["query"])
        self.assertEqual(1, rows[0]["query_index"])
        self.assertEqual(1, rows[0]["page"])
        self.assertEqual(1, rows[0]["position"])

        self.assertEqual("query-two", rows[1]["query"])
        self.assertEqual(2, rows[1]["query_index"])
        self.assertEqual(1, rows[1]["page"])
        self.assertEqual(2, rows[1]["position"])

        expected_calls = [
            mock.call(query="query-one", cfg=cfg, page=1, results_per_page=30),
            mock.call(query="query-one", cfg=cfg, page=2, results_per_page=30),
            mock.call(query="query-two", cfg=cfg, page=1, results_per_page=30),
            mock.call(query="query-two", cfg=cfg, page=2, results_per_page=30),
        ]
        self.assertEqual(expected_calls, fetch_mock.call_args_list)


class FetcherSelectionTests(unittest.TestCase):
    def test_resolve_fetcher_http_returns_default_fetch_function(self):
        with erp_scraper.resolve_fetcher(engine="http", headed=False) as fetch_html:
            self.assertIs(fetch_html, erp_scraper.fetch_ddg_html)

    def test_resolve_fetcher_playwright_uses_fetcher_and_closes(self):
        with mock.patch("erp_scraper.PlaywrightFetcher") as fetcher_cls:
            fetcher_instance = fetcher_cls.return_value

            with erp_scraper.resolve_fetcher(engine="playwright", headed=True) as fetch_html:
                self.assertIs(fetch_html, fetcher_instance.fetch_ddg_html)

            fetcher_cls.assert_called_once_with(headed=True)
            fetcher_instance.close.assert_called_once()

    def test_resolve_fetcher_invalid_engine_raises(self):
        with self.assertRaises(ValueError) as ctx:
            with erp_scraper.resolve_fetcher(engine="invalid", headed=False):
                pass

        self.assertIn("Unknown engine", str(ctx.exception))


class PlaywrightFetcherBehaviorTests(unittest.TestCase):
    def test_headed_mode_falls_back_to_headless_when_no_display_on_linux(self):
        fake_timeout_error = type("FakeTimeoutError", (Exception,), {})
        fake_sync_playwright = mock.Mock()
        playwright_instance = mock.Mock()
        browser_instance = mock.Mock()
        context_instance = mock.Mock()

        fake_sync_playwright.start.return_value = playwright_instance
        playwright_instance.chromium.launch.return_value = browser_instance
        browser_instance.new_context.return_value = context_instance

        fake_sync_api = types.SimpleNamespace(
            TimeoutError=fake_timeout_error,
            sync_playwright=mock.Mock(return_value=fake_sync_playwright),
        )

        with mock.patch.dict(sys.modules, {"playwright.sync_api": fake_sync_api}):
            with mock.patch.object(erp_scraper.sys, "platform", "linux"), mock.patch.dict(
                erp_scraper.os.environ,
                {},
                clear=True,
            ):
                fetcher = erp_scraper.PlaywrightFetcher(headed=True)
                fetcher._ensure_started()

                playwright_instance.chromium.launch.assert_called_once_with(headless=True)
                fetcher.close()

    def test_startup_failure_stops_playwright_before_retry(self):
        fake_timeout_error = type("FakeTimeoutError", (Exception,), {})
        fake_sync_playwright = mock.Mock()
        playwright_instance = mock.Mock()

        fake_sync_playwright.start.return_value = playwright_instance
        playwright_instance.chromium.launch.side_effect = RuntimeError("launch failed")

        fake_sync_api = types.SimpleNamespace(
            TimeoutError=fake_timeout_error,
            sync_playwright=mock.Mock(return_value=fake_sync_playwright),
        )

        with mock.patch.dict(sys.modules, {"playwright.sync_api": fake_sync_api}):
            fetcher = erp_scraper.PlaywrightFetcher(headed=False)

            with self.assertRaises(RuntimeError):
                fetcher._ensure_started()

        playwright_instance.stop.assert_called_once()
        self.assertIsNone(fetcher._playwright)
        self.assertIsNone(fetcher._browser)
        self.assertIsNone(fetcher._context)


class PathAndParserTests(unittest.TestCase):
    def test_resolve_output_path_uses_slug_json(self):
        path = erp_scraper.resolve_output_path("frontend-remote", Path("data/results"))

        self.assertEqual(Path("data/results/frontend-remote.json"), path)

    def test_parse_ddg_results_extracts_snippet_and_domain(self):
        html = """
        <html>
          <body>
            <a class=\"result__a\" href=\"https://example.com/jobs/123\">Senior <b>Frontend</b> Engineer</a>
            <a class=\"result__snippet\">Remote role with React and TypeScript</a>

            <a class=\"result__a\" href=\"//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.greenhouse.io%2Fjobs%2F456&rut=abc\">Greenhouse listing</a>
            <div class=\"result__snippet\">Apply now for remote team</div>
          </body>
        </html>
        """

        rows = erp_scraper.parse_ddg_results(html)

        self.assertEqual(2, len(rows))

        first = rows[0]
        self.assertEqual(1, first["position"])
        self.assertEqual("Senior Frontend Engineer", first["title"])
        self.assertEqual("https://example.com/jobs/123", first["url"])
        self.assertEqual("example.com", first["domain"])
        self.assertEqual("Remote role with React and TypeScript", first["snippet"])

        second = rows[1]
        self.assertEqual(2, second["position"])
        self.assertEqual("https://www.greenhouse.io/jobs/456", second["url"])
        self.assertEqual("greenhouse.io", second["domain"])
        self.assertEqual("Apply now for remote team", second["snippet"])


class LoadSearchTermsTests(unittest.TestCase):
    def test_load_search_terms_from_file(self):
        payload = [
            {
                "title": "Backend Python Remote",
                "queries": [
                    "site:jobs.lever.co \"python\" \"remote\"",
                    "site:dice.com \"python\" \"remote\"",
                ],
                "output": "backend-python-remote",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "search_terms.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            terms = erp_scraper.load_search_terms(path)

        self.assertEqual(1, len(terms))
        self.assertEqual("backend-python-remote", terms[0].output)
        self.assertEqual(2, len(terms[0].queries))


class SerperEngineTests(unittest.TestCase):
    def test_parse_serper_results_maps_fields(self):
        raw = {
            "organic": [
                {
                    "position": 3,
                    "title": "Apple jobs",
                    "link": "https://www.apple.com/careers/us/",
                    "snippet": "Open roles at Apple.",
                }
            ]
        }

        rows = erp_scraper.parse_serper_results(raw)

        self.assertEqual(1, len(rows))
        self.assertEqual(3, rows[0]["position"])
        self.assertEqual("Apple jobs", rows[0]["title"])
        self.assertEqual("https://www.apple.com/careers/us/", rows[0]["url"])
        self.assertEqual("apple.com", rows[0]["domain"])
        self.assertEqual("Open roles at Apple.", rows[0]["snippet"])

    def test_collect_results_for_queries_serper_stops_on_empty_page(self):
        cfg = erp_scraper.Config(min_delay=0, max_delay=0, max_retries=1, timeout=1)

        fake_batches = {
            "query-one": [
                {"organic": [{"position": 1, "title": "A", "link": "https://example.com/a", "snippet": "sa"}]},
                {"organic": []},
                {"organic": [{"position": 1, "title": "IGNORED", "link": "https://example.com/ignored", "snippet": "x"}]},
            ],
            "query-two": [
                {"organic": [{"position": 1, "title": "B", "link": "https://example.com/b", "snippet": "sb"}]},
                {"organic": []},
                {"organic": []},
            ],
        }

        with mock.patch(
            "erp_scraper.fetch_serper_batch_payloads",
            side_effect=lambda batch_payload, cfg, api_key: fake_batches[batch_payload[0]["q"]],
        ) as fetch_mock, mock.patch(
            "erp_scraper.sleep_between_requests",
            return_value=None,
        ):
            rows, errors = erp_scraper.collect_results_for_queries_serper(
                queries=["query-one", "query-two"],
                cfg=cfg,
                pages=3,
                results_per_page=10,
                api_key="token",
            )

        self.assertEqual([], errors)
        self.assertEqual(2, len(rows))
        self.assertEqual(1, rows[0]["position"])
        self.assertEqual(2, rows[1]["position"])
        self.assertEqual("query-two", rows[1]["query"])

        expected_calls = [
            mock.call(
                batch_payload=[
                    {"q": "query-one", "page": 1, "num": 10},
                    {"q": "query-one", "page": 2, "num": 10},
                    {"q": "query-one", "page": 3, "num": 10},
                ],
                cfg=cfg,
                api_key="token",
            ),
            mock.call(
                batch_payload=[
                    {"q": "query-two", "page": 1, "num": 10},
                    {"q": "query-two", "page": 2, "num": 10},
                    {"q": "query-two", "page": 3, "num": 10},
                ],
                cfg=cfg,
                api_key="token",
            ),
        ]
        self.assertEqual(expected_calls, fetch_mock.call_args_list)

    def test_normalize_serper_batch_response_pads_missing_items(self):
        raw = {"organic": [{"title": "Only one"}]}
        rows = erp_scraper.normalize_serper_batch_response(raw, expected_items=3)

        self.assertEqual(3, len(rows))
        self.assertEqual(raw, rows[0])
        self.assertEqual({}, rows[1])
        self.assertEqual({}, rows[2])


class DotenvTests(unittest.TestCase):
    def test_load_dotenv_sets_missing_values_without_overriding_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "SERPER_API_KEY=from-file\nALREADY=from-file\nQUOTED='hello world'\n# COMMENTED=1\n",
                encoding="utf-8",
            )

            with mock.patch.dict(erp_scraper.os.environ, {"ALREADY": "from-env"}, clear=True):
                erp_scraper.load_dotenv(env_path)

                self.assertEqual("from-file", erp_scraper.os.environ["SERPER_API_KEY"])
                self.assertEqual("from-env", erp_scraper.os.environ["ALREADY"])
                self.assertEqual("hello world", erp_scraper.os.environ["QUOTED"])

    def test_resolve_serper_api_key_raises_when_missing(self):
        with mock.patch.dict(erp_scraper.os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                erp_scraper.resolve_serper_api_key()

        self.assertIn("SERPER_API_KEY is missing", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
