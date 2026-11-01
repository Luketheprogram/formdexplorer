"""Read-only public release audit. No login, tracking, billing or mutation calls.

Run: .venv/bin/python scripts/audit_public_quality.py --base https://formdexplorer.com
Fetches one page per public route family and robots/sitemap/ads metadata. Reports
observations, not Google account state or a guarantee of crawl/indexing behavior.
"""
import argparse
import json
from urllib.parse import urlsplit
from xml.etree import ElementTree

import requests
from lxml import html


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="https://formdexplorer.com")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path:
        parser.error("--base must be an absolute origin")
    session = requests.Session()
    session.headers["User-Agent"] = "FormDExplorer-PublicQualityAudit/1.0"
    results = []
    paths = ["/", "/learn/", "/learn/how-to-read-a-form-d/", "/state/CA/", "/industry/biotechnology/",
             "/research/", "/research/filing-activity/", "/research/amendments/", "/research/coverage/",
             "/about/", "/editorial/", "/search/", "/adv/", "/cf/", "/1a/", "/pricing/",
             "/privacy/", "/terms/", "/login/", "/robots.txt", "/sitemap.xml", "/ads.txt"]
    for path in paths:
        item = {"path": path}
        try:
            response = session.get(base + path, timeout=30)
            item.update(status=response.status_code, final_url=response.url,
                        robots_header=response.headers.get("X-Robots-Tag"), bytes=len(response.content))
            if "text/html" in response.headers.get("Content-Type", ""):
                doc = html.fromstring(response.content)
                item.update(title=doc.xpath('//title/text()'), canonical=doc.xpath('//link[@rel="canonical"]/@href'),
                            robots_meta=doc.xpath('//meta[@name="robots"]/@content'), h1_count=len(doc.xpath('//h1')),
                            publisher_verification=bool(doc.xpath('//meta[@name="google-adsense-account"]')),
                            ad_slots=len(doc.xpath('//*[@data-ad-slot]')),
                            research_navigation=bool(doc.xpath('//a[@href="/research/"]')))
                item["structured_data_valid"] = True
                for script in doc.xpath('//script[@type="application/ld+json"]/text()'):
                    try:
                        json.loads(script)
                    except ValueError:
                        item["structured_data_valid"] = False
            elif path == "/sitemap.xml":
                root = ElementTree.fromstring(response.content)
                item["sitemap_sections"] = [node.text for node in root.iter() if node.tag.endswith("}loc")]
            else:
                item["public_text"] = response.text[:1000]
        except (requests.RequestException, ValueError, ElementTree.ParseError) as exc:
            item["error"] = str(exc)
        results.append(item)
    print(json.dumps({"base": base, "observations": results}, indent=2))


if __name__ == "__main__":
    main()
