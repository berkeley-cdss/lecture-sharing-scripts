"""
Ensure every lecture webcast in webcasts.csv has a corresponding Canvas page
with an embedded Kaltura player.

Reads webcasts.csv, checks existing Canvas pages, and creates missing ones.
Uses the Canvas LTI Resource Links API to create proper Kaltura embeds.

Env vars:
  - CANVAS_API_TOKEN: a Canvas (bCourses) access token
"""

import argparse
import csv
import os
import re

import requests
from ruamel.yaml import YAML

CANVAS_BASE = "https://bcourses.berkeley.edu"
KALTURA_TOOL_ID = 90481
PLAYER_SKIN = "51825692"


def get_existing_pages(session, course_id):
    """Get all existing pages in the course. Returns dict of slug -> page."""
    pages = {}
    url = f"{CANVAS_BASE}/api/v1/courses/{course_id}/pages"
    while url:
        resp = session.get(url, params={"per_page": 100}, timeout=30)
        resp.raise_for_status()
        for page in resp.json():
            pages[page["url"]] = page
        links = resp.headers.get("Link", "")
        next_match = re.search(r'<([^>]+)>;\s*rel="next"', links)
        url = next_match.group(1) if next_match else None
    return pages


def create_resource_link(session, course_id, entry_id, title):
    """Create a Canvas LTI resource link for a Kaltura entry.

    Returns the lookup_uuid needed for the embed iframe.
    """
    kaf_url = (
        f"https://kaf.berkeley.edu/browseandembed/index/media"
        f"/entryid/{entry_id}"
        f"/showDescription/false/showTitle/false/showTags/false"
        f"/showDuration/false/showOwner/false/showUploadDate/false"
        f"/playerSize/608x342/playerSkin/{PLAYER_SKIN}/"
    )
    resp = session.post(
        f"{CANVAS_BASE}/api/v1/courses/{course_id}/lti_resource_links",
        json={
            "url": kaf_url,
            "title": title,
            "context_external_tool_id": KALTURA_TOOL_ID,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["lookup_uuid"]


def build_embed_body(course_id, lookup_uuid, title):
    """Build the page HTML body with a Canvas-authenticated Kaltura embed."""
    embed_src = (
        f"https://bcourses.berkeley.edu/courses/{course_id}"
        f"/external_tools/retrieve?display=in_rce"
        f"&amp;resource_link_lookup_uuid={lookup_uuid}"
    )
    return (
        f'<div class="dp-embed-wrapper">'
        f'<iframe style="width: 608px; height: 342px;" '
        f'title="{title}" '
        f'src="{embed_src}" '
        f'loading="lazy" allowfullscreen="allowfullscreen" '
        f'allow="geolocation *; microphone *; camera *; midi *; '
        f'encrypted-media *; autoplay *; clipboard-write *; display-capture *">'
        f"</iframe></div>"
    )


def create_page(session, course_id, title, body):
    """Create a new published Canvas page."""
    resp = session.post(
        f"{CANVAS_BASE}/api/v1/courses/{course_id}/pages",
        json={
            "wiki_page": {
                "title": title,
                "body": body,
                "published": True,
            }
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def parse_lecture_number(title):
    """Extract lecture number from a webcast title. Returns None if not a lecture."""
    match = re.search(r"Lecture\s+(\d+)", title)
    return int(match.group(1)) if match else None


def build_lecture_to_date_map(weeks_yml_path):
    """Read weeks.yml and map lecture number -> date string.

    Lectures are numbered sequentially, skipping holidays and entries without titles.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    with open(weeks_yml_path, "r", encoding="utf-8") as f:
        data = yaml.load(f)

    lecture_map = {}
    lec_num = 0
    for entry in data:
        if entry.get("type") != "lec":
            continue
        if entry.get("holiday") or not entry.get("title"):
            continue
        lec_num += 1
        lecture_map[lec_num] = str(entry["date"])
    return lecture_map


def main():
    parser = argparse.ArgumentParser(
        description="Sync webcast pages on Canvas"
    )
    parser.add_argument("--course-id", default="1551726")
    parser.add_argument(
        "--webcasts-csv",
        default=os.path.join(os.path.dirname(__file__), "..", "_data", "webcasts.csv"),
    )
    parser.add_argument(
        "--weeks-yml",
        default=os.path.join(
            os.path.dirname(__file__), "..", "_data", "materials", "weeks.yml"
        ),
    )
    parser.add_argument(
        "--output",
        default=os.path.join(os.path.dirname(__file__), "..", "_data", "webcast_pages.csv"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without actually creating pages",
    )
    args = parser.parse_args()

    token = os.environ.get("CANVAS_API_TOKEN")
    if not token:
        raise RuntimeError("CANVAS_API_TOKEN must be set")

    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    # Load webcasts
    csv_path = os.path.abspath(args.webcasts_csv)
    with open(csv_path, "r", encoding="utf-8") as f:
        webcasts = list(csv.DictReader(f))

    # Filter to lectures only
    lectures = []
    for w in webcasts:
        lec_num = parse_lecture_number(w["title"])
        if lec_num is not None:
            entry_id = re.search(r"/media/t/([^/]+)", w["url"]).group(1)
            lectures.append({
                "number": lec_num,
                "title": w["title"],
                "entry_id": entry_id,
                "page_title": f"Lecture {lec_num}",
                "page_slug": f"lecture-{lec_num}",
            })

    print(f"Found {len(lectures)} lectures in webcasts.csv")

    # Build lecture number -> date mapping from weeks.yml
    lecture_dates = build_lecture_to_date_map(os.path.abspath(args.weeks_yml))

    # Get existing pages
    existing = get_existing_pages(session, args.course_id)
    print(f"Found {len(existing)} existing pages on Canvas\n")

    created = []
    skipped = []
    csv_rows = []

    for lec in sorted(lectures, key=lambda l: l["number"]):
        slug = lec["page_slug"]

        if slug in existing:
            print(f"  {lec['page_title']}: already exists, skipping")
            skipped.append(lec)
            page_slug = slug
        elif args.dry_run:
            print(f"  {lec['page_title']}: would create (entry {lec['entry_id']})")
            created.append(lec)
            page_slug = slug
        else:
            # Create LTI resource link for Kaltura embed
            lookup_uuid = create_resource_link(
                session, args.course_id, lec["entry_id"], lec["title"]
            )

            # Build page body with the resource link embed
            body = build_embed_body(args.course_id, lookup_uuid, lec["title"])

            # Create the Canvas page
            page = create_page(session, args.course_id, lec["page_title"], body)
            page_slug = page["url"]
            print(f"  {lec['page_title']}: created -> {page_slug}")
            created.append(lec)

        # Add to CSV output
        date = lecture_dates.get(lec["number"])
        if date:
            page_url = (
                f"{CANVAS_BASE}/courses/{args.course_id}/pages/{page_slug}"
            )
            csv_rows.append({"date": date, "url": page_url})

    # Write CSV
    output_path = os.path.abspath(args.output)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "url"])
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"\nWrote {len(csv_rows)} entries to {output_path}")
    print(f"Done: {len(created)} created, {len(skipped)} already existed")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"created={len(created)}\n")


if __name__ == "__main__":
    main()
