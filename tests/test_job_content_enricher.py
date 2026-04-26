import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import erp_scraper
import job_content_enricher


class LoadRowsTests(unittest.TestCase):
    def test_load_rows_accepts_list_of_objects(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rows.json"
            path.write_text(json.dumps([{"url": "https://example.com"}]), encoding="utf-8")

            rows = job_content_enricher.load_rows(path)

        self.assertEqual(1, len(rows))
        self.assertEqual("https://example.com", rows[0]["url"])

    def test_load_rows_rejects_non_array(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rows.json"
            path.write_text(json.dumps({"url": "https://example.com"}), encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                job_content_enricher.load_rows(path)

        self.assertIn("JSON array", str(ctx.exception))


class ResolveResultPathsTests(unittest.TestCase):
    def test_resolve_result_paths_uses_config_outputs(self):
        terms = [
            erp_scraper.SearchTerm(title="A", queries=["q"], output="frontend-remote"),
            erp_scraper.SearchTerm(title="B", queries=["q2"], output="backend-remote"),
        ]

        with mock.patch("job_content_enricher.erp_scraper.load_search_terms", return_value=terms):
            paths = job_content_enricher.resolve_result_paths(
                config_path=Path("data/queries/search_terms.json"),
                results_dir=Path("data/results"),
            )

        self.assertEqual(
            [Path("data/results/frontend-remote.json"), Path("data/results/backend-remote.json")],
            paths,
        )


class EnrichResultFileTests(unittest.TestCase):
    def test_enrich_result_file_writes_enriched_rows(self):
        cfg = erp_scraper.Config(min_delay=0, max_delay=0, max_retries=1, timeout=1)
        initial_rows = [{"url": "https://example.com/jobs/1", "title": "Role"}]
        enriched_rows = [{"url": "https://example.com/jobs/1", "title": "Role", "job_description": "Desc"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rows.json"
            path.write_text(json.dumps(initial_rows), encoding="utf-8")

            with mock.patch(
                "job_content_enricher.enrich_rows_with_job_content_batched",
                return_value=(enriched_rows, []),
            ) as enrich_mock:
                row_count, error_count = job_content_enricher.enrich_result_file(
                    path=path,
                    cfg=cfg,
                    max_chars=4000,
                    batch_size=20,
                )

            saved_rows = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(1, row_count)
        self.assertEqual(0, error_count)
        self.assertEqual("Desc", saved_rows[0]["job_description"])
        enrich_mock.assert_called_once_with(rows=initial_rows, cfg=cfg, max_chars=4000, batch_size=20)


class BatchedEnrichmentTests(unittest.TestCase):
    def test_batched_enrichment_reuses_result_for_duplicate_url(self):
        cfg = erp_scraper.Config(min_delay=0, max_delay=0, max_retries=1, timeout=1)
        rows = [
            {"url": "https://example.com/jobs/1", "title": "A"},
            {"url": "https://example.com/jobs/2", "title": "B"},
            {"url": "https://example.com/jobs/1", "title": "C"},
            {"title": "Missing URL"},
        ]

        def fake_process(url: str, cfg: erp_scraper.Config, max_chars: int):
            details = {
                "job_description": f"Desc for {url}",
                "job_requirements": "Req",
                "job_content_source": "unit-test",
                "job_fetch_status": "ok",
                "job_fetch_error": "",
                "job_fetch_http_status": 200,
                "job_fetch_url": url,
            }
            return details, None

        with mock.patch("job_content_enricher._process_url_sync", side_effect=fake_process) as process_mock:
            enriched_rows, errors = job_content_enricher.enrich_rows_with_job_content_batched(
                rows=rows,
                cfg=cfg,
                max_chars=4000,
                batch_size=2,
            )

        self.assertEqual([], errors)
        self.assertEqual(2, process_mock.call_count)
        self.assertEqual("Desc for https://example.com/jobs/1", enriched_rows[0]["job_description"])
        self.assertEqual("Desc for https://example.com/jobs/2", enriched_rows[1]["job_description"])
        self.assertEqual("Desc for https://example.com/jobs/1", enriched_rows[2]["job_description"])
        self.assertEqual("skipped", enriched_rows[3]["job_fetch_status"])

    def test_batched_enrichment_collects_url_errors(self):
        cfg = erp_scraper.Config(min_delay=0, max_delay=0, max_retries=1, timeout=1)
        rows = [
            {"url": "https://example.com/jobs/ok"},
            {"url": "https://example.com/jobs/fail"},
        ]

        def fake_process(url: str, cfg: erp_scraper.Config, max_chars: int):
            if url.endswith("/fail"):
                return (
                    {
                        "job_description": "",
                        "job_requirements": "",
                        "job_content_source": "none",
                        "job_fetch_status": "error",
                        "job_fetch_error": "RuntimeError: failed",
                        "job_fetch_http_status": None,
                        "job_fetch_url": "",
                    },
                    f"url={url}: RuntimeError: failed",
                )

            return (
                {
                    "job_description": "ok",
                    "job_requirements": "",
                    "job_content_source": "unit-test",
                    "job_fetch_status": "ok",
                    "job_fetch_error": "",
                    "job_fetch_http_status": 200,
                    "job_fetch_url": url,
                },
                None,
            )

        with mock.patch("job_content_enricher._process_url_sync", side_effect=fake_process):
            enriched_rows, errors = job_content_enricher.enrich_rows_with_job_content_batched(
                rows=rows,
                cfg=cfg,
                max_chars=4000,
                batch_size=2,
            )

        self.assertEqual(1, len(errors))
        self.assertIn("/fail", errors[0])
        self.assertEqual("ok", enriched_rows[0]["job_fetch_status"])
        self.assertEqual("error", enriched_rows[1]["job_fetch_status"])


if __name__ == "__main__":
    unittest.main()
