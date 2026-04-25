#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import json
import random
import time
from dataclasses import dataclass
from typing import List, Dict, Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import re


@dataclass
class Config:
    min_delay: float = 2.0
    max_delay: float = 6.0
    max_retries: int = 4
    backoff_base: float = 1.8
    timeout: int = 20


UA_LIST = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
]


class CaptchaDetected(Exception):
    pass


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
    return any(s in low for s in signals)


def build_ddh_url(query: str) -> str:
    base = "https://duckduckgo.com/html/"
    normalized_query = query.replace("site:https://", "site:").replace("site:http://", "site:")
    return f"{base}?{urlencode({'q': normalized_query})}"


def fetch_ddg_html(query: str, cfg: Config) -> str:
    """
    DuckDuckGo HTML endpoint (text-like results page).
    """
    url = build_ddh_url(query)

    for attempt in range(cfg.max_retries):
        headers = {
            "User-Agent": random.choice(UA_LIST),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        }
        req = Request(url, headers=headers)

        try:
            with urlopen(req, timeout=cfg.timeout) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            print(html)

            if looks_like_captcha(html):
                print(f"[CAPTCHA]")
                raise CaptchaDetected("CAPTCHA detectado. Interrompendo para evitar violação de proteção anti-bot.")

            return html

        except HTTPError as e:
            # 429/503 comuns em rate limit
            if e.code in (429, 503) and attempt < cfg.max_retries - 1:
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


def parse_ddg_results(html: str) -> List[Dict[str, Any]]:
    """
    Parser simples por regex para links com class result__a.
    (rápido e sem dependências externas)
    """
    pattern = re.compile(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.I | re.S,
    )

    results = []
    for idx, m in enumerate(pattern.finditer(html), start=1):
        href = m.group(1).strip()
        title_html = m.group(2)
        title = re.sub(r"<[^>]+>", "", title_html)
        title = " ".join(title.split())

        results.append(
            {
                "position": idx,
                "title": title,
                "url": href,
            }
        )
    return results


def save_json(rows: List[Dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def save_csv(rows: List[Dict[str, Any]], path: str) -> None:
    if not rows:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["position", "title", "url"])
        return

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["position", "title", "url"])
        writer.writeheader()
        writer.writerows(rows)


def run(query: str, out_prefix: str, cfg: Config) -> None:
    print(f"[INFO] Query: {query}")
    html = fetch_ddg_html(query, cfg)
    rows = parse_ddg_results(html)

    json_path = f"{out_prefix}.json"
    csv_path = f"{out_prefix}.csv"

    save_json(rows, json_path)
    save_csv(rows, csv_path)

    print(f"[OK] Resultados: {len(rows)}")
    print(f"[OK] JSON: {json_path}")
    print(f"[OK] CSV:  {csv_path}")

    # Espera aleatória (boas práticas)
    delay = random.uniform(cfg.min_delay, cfg.max_delay)
    print(f"[INFO] Sleeping {delay:.2f}s")
    time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description="SERP scraper simples e compliance-first.")
    parser.add_argument("--query", required=True, help="Termo de busca")
    parser.add_argument("--out", default="results", help="Prefixo dos arquivos de saída")
    parser.add_argument("--min-delay", type=float, default=2.0)
    parser.add_argument("--max-delay", type=float, default=6.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=20)

    args = parser.parse_args()

    cfg = Config(
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        max_retries=args.retries,
        timeout=args.timeout,
    )

    try:
        run(args.query, args.out, cfg)
    except CaptchaDetected as e:
        print(f"[STOP] {e}")
        print("[DICA] Use API de SERP para produção (estabilidade maior).")
    except Exception as e:
        print(f"[ERRO] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()