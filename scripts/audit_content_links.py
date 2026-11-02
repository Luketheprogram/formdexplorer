"""Bounded, read-only public metadata/link/redirect audit. No authenticated actions."""

import argparse
import json
from collections import deque
from urllib.parse import urljoin, urlsplit

import requests
from lxml import html

SKIP = (
    "/admin",
    "/accounts",
    "/export",
    "/checkout",
    "/logout",
    "/unsubscribe",
    "/subscribe",
    "/research/exports",
    "/research/collections",
    "/research/items",
    "/research/operations",
    "/research/feedback",
    "/api/",
)
START = [
    "/",
    "/research/",
    "/research/workbench/",
    "/research/calendar/",
    "/research/fields/",
    "/research/glossary/",
    "/learn/",
    "/about/",
    "/editorial/",
    "/privacy/",
    "/terms/",
    "/search/",
    "/cf/",
    "/1a/",
    "/adv/",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="https://formdexplorer.com")
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 300:
        parser.error("Use a limit of 1–300 pages.")
    origin = args.base.rstrip("/")
    session = requests.Session()
    session.headers["User-Agent"] = "FormDExplorer-PublicQualityAudit/2.0"
    queue, seen, rows = deque(START), set(), []
    while queue and len(seen) < args.limit:
        path = queue.popleft()
        if path in seen:
            continue
        seen.add(path)
        item = {"path": path}
        try:
            r = session.get(origin + path, timeout=30)
            item.update(
                status=r.status_code, redirect_count=len(r.history), final_url=r.url
            )
            if (
                "text/html" in r.headers.get("Content-Type", "")
                and r.status_code == 200
            ):
                doc = html.fromstring(r.content)
                item.update(
                    title=doc.xpath("string(//title)"),
                    description=doc.xpath(
                        'string(//meta[@name="description"]/@content)'
                    ),
                    canonical=doc.xpath('//link[@rel="canonical"]/@href'),
                    h1_count=len(doc.xpath("//h1")),
                    noindex=bool(
                        doc.xpath(
                            '//meta[@name="robots" and contains(@content,"noindex")]'
                        )
                    ),
                    ad_slots=len(doc.xpath("//*[@data-ad-slot]")),
                )
                for href in doc.xpath("//main//a/@href"):
                    url = urlsplit(urljoin(origin + path, href))
                    if (
                        url.netloc != urlsplit(origin).netloc
                        or url.query
                        or url.path.startswith(SKIP)
                        or url.path.startswith("/static/")
                        or "/download/" in url.path
                        or "/source/" in url.path
                    ):
                        continue
                    if url.path not in seen:
                        queue.append(url.path)
        except (requests.RequestException, ValueError) as exc:
            item["error"] = type(exc).__name__
        rows.append(item)
    duplicates = {}
    for key in ("title", "description"):
        grouped = {}
        for row in rows:
            if row.get(key) and not row.get("noindex"):
                grouped.setdefault(row[key], []).append(row["path"])
        duplicates[key] = [paths for paths in grouped.values() if len(paths) > 1]
    problems = [
        row
        for row in rows
        if row.get("error")
        or row.get("status", 500) >= 400
        or row.get("redirect_count", 0) > 1
        or row.get("ad_slots", 0)
        or ("h1_count" in row and row["h1_count"] != 1)
    ]
    report = {
        "scope": "Bounded public GET crawl; no authenticated actions or external-domain link checking. Bot-blocked external sources are not classified as dead links.",
        "observations": rows,
        "duplicates": duplicates,
        "problems": problems,
        "remaining_queue": len(queue),
    }
    from pathlib import Path

    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "pages": len(rows),
                "problems": len(problems),
                "duplicate_groups": sum(map(len, duplicates.values())),
            }
        )
    )


if __name__ == "__main__":
    main()
