"""Read-only release smoke test. Run from the repo with .venv/bin/python.

Use --base http://127.0.0.1:8766 for a seeded local preview. An optional
--all-sitemaps checks every batch sequentially; default checks the index only.
No crawling of individual dataset records, accounts, exports or checkout.
"""
import argparse
import json
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import requests
from lxml import html


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="https://formdexplorer.com")
    parser.add_argument("--all-sitemaps", action="store_true")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    session = requests.Session()
    session.headers["User-Agent"] = "FormDExplorer-SEO-Check/1.0"
    results = []
    def check(label, passed):
        results.append({"check": label, "passed": bool(passed)})
    for path in ["/", "/states/", "/industries/", "/learn/", "/recent/",
                 "/learn/form-d-data-methodology/", "/learn/research-company-form-d-history/",
                 "/learn/form-d-offering-amount-vs-amount-sold/"]:
        r = session.get(base + path, timeout=45)
        check(path + " status", r.status_code == 200)
        doc = html.fromstring(r.content)
        check(path + " canonical", doc.xpath('//link[@rel="canonical"]/@href') == [base + path])
        check(path + " metadata", bool(doc.xpath('//title/text()')) and bool(doc.xpath('//meta[@name="description"]/@content')))
        check(path + " heading", len(doc.xpath('//h1')) == 1)
        check(path + " indexable", "noindex" not in r.headers.get("X-Robots-Tag", "") and
              not any("noindex" in x for x in doc.xpath('//meta[@name="robots"]/@content')))
        graphs = [json.loads(x) for x in doc.xpath('//script[@type="application/ld+json"]/text()')]
        check(path + " JSON-LD", any("@graph" in x for x in graphs))
    r = session.get(base + "/robots.txt", timeout=45)
    check("robots sitemap", r.status_code == 200 and f"Sitemap: {base}/sitemap.xml" in r.text)
    r = session.get(base + "/sitemap.xml", timeout=45)
    root = ET.fromstring(r.content)
    check("sitemap index", r.status_code == 200 and root.tag.endswith("}sitemapindex"))
    urls = [x.text for x in root.iter() if x.tag.endswith("}loc")]
    check("sitemap section origins", bool(urls) and all(x.startswith(base + "/sitemap-") for x in urls))
    total = 0
    seen = set()
    if args.all_sitemaps:
        for url in urls:
            # Never follow an unexpected origin advertised by a broken sitemap.
            if not url.startswith(base + "/sitemap-"):
                continue
            r = session.get(url, timeout=45)
            section = ET.fromstring(r.content)
            locs = [x.text for x in section.iter() if x.tag.endswith("}loc")]
            check(url + " valid", r.status_code == 200 and section.tag.endswith("}urlset"))
            check(url + " bounded", len(locs) <= 5000)
            check(url + " canonical", all(x.startswith(base + "/") and not urlsplit(x).query for x in locs))
            check(url + " unique", len(locs) == len(set(locs)) and not seen.intersection(locs))
            seen.update(locs)
            total += len(locs)
    print(json.dumps({"base": base, "checks": results, "child_sitemaps": len(urls),
                      "checked_content_urls": total, "failed": sum(not r["passed"] for r in results)}, indent=2))
    return int(any(not r["passed"] for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
