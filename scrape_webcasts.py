"""
Scrape lecture webcast URLs from Kaltura via Canvas (bCourses) and write to CSV.

Authenticates using a Canvas API access token, launches the Kaltura external tool
via Canvas's sessionless_launch API, then scrapes the channel gallery.

Env vars:
  - CANVAS_API_TOKEN: a Canvas (bCourses) access token
"""

import argparse
import csv
import os
import re

import requests
from bs4 import BeautifulSoup

CANVAS_BASE = "https://bcourses.berkeley.edu"


def get_sessionless_launch_url(token, course_id, tool_id):
    """Use the Canvas API to get a sessionless launch URL for the external tool."""
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"
    resp = session.get(
        f"{CANVAS_BASE}/api/v1/courses/{course_id}/external_tools/sessionless_launch",
        params={"id": tool_id},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["url"]


def complete_lti_flow(launch_url):
    """Follow the LTI 1.3 OIDC flow to get an authenticated Kaltura session."""
    session = requests.Session()

    # Step 1: Load the launch page (contains OIDC init form)
    resp = session.get(launch_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form")
    params = {
        inp.get("name"): inp.get("value", "")
        for inp in form.find_all("input")
        if inp.get("name")
    }

    # Step 2: Submit OIDC init -> Canvas auth page with response form
    resp2 = session.post(form["action"], data=params, timeout=30)
    resp2.raise_for_status()
    soup2 = BeautifulSoup(resp2.text, "html.parser")
    form2 = soup2.find("form")
    params2 = {
        inp.get("name"): inp.get("value", "")
        for inp in form2.find_all("input")
        if inp.get("name")
    }

    # Step 3: Submit auth response -> lands on Kaltura
    session.post(form2["action"], data=params2, timeout=30)

    return session


def scrape_channel(session, channel_path):
    """Paginate through a Kaltura channel gallery and extract entries."""
    all_results = []
    seen = set()
    page = 1

    while True:
        url = f"https://kaf.berkeley.edu{channel_path}/page/{page}"
        resp = session.get(url, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")

        items = soup.select("li.galleryItem")
        new_count = 0
        for item in items:
            thumb = item.select_one("div.photo-group")
            title = thumb.get("title", "").strip() if thumb else ""
            link = item.select_one('a.item_link[href*="/media/t/"]')
            if not link:
                continue
            match = re.search(r"/media/t/([01]_[a-z0-9]+)", link["href"])
            if not match or match.group(1) in seen:
                continue
            entry_id = match.group(1)
            seen.add(entry_id)
            new_count += 1
            all_results.append({
                "title": title,
                "url": f"https://kaf.berkeley.edu/media/t/{entry_id}/{channel_path.split('/')[-1]}",
            })

        if new_count == 0:
            break
        page += 1

    return all_results


def main():
    parser = argparse.ArgumentParser(description="Scrape Kaltura webcasts via Canvas")
    parser.add_argument("--course-id", default="1551726")
    parser.add_argument("--tool-id", default="90481")
    parser.add_argument("--channel-path", default="/channel/1551726/397920713")
    parser.add_argument(
        "--output",
        default=os.path.join(os.path.dirname(__file__), "..", "_data", "webcasts.csv"),
    )
    args = parser.parse_args()

    token = os.environ.get("CANVAS_API_TOKEN")
    if not token:
        raise RuntimeError("CANVAS_API_TOKEN must be set")

    print("Getting sessionless launch URL from Canvas API...")
    launch_url = get_sessionless_launch_url(token, args.course_id, args.tool_id)

    print("Completing LTI launch flow...")
    session = complete_lti_flow(launch_url)

    print(f"Scraping channel {args.channel_path}...")
    results = scrape_channel(session, args.channel_path)
    print(f"Found {len(results)} entries.")

    for r in results:
        print(f"  {r['title']}")

    output = os.path.abspath(args.output)
    with open(output, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "url"])
        writer.writeheader()
        writer.writerows(results)

    print(f"\nWrote {len(results)} entries to {output}")

    # GitHub Actions output
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"count={len(results)}\n")


if __name__ == "__main__":
    main()
