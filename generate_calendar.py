#!/usr/bin/env python3
"""
Fetches CSO release calendar and generates iCal invites for Economy
and Labour Market and Earnings releases in the next 8 days.
"""

import json
import urllib.request
from datetime import datetime, timedelta, timezone
import uuid
import sys

CALENDAR_JSON_URL = "https://cdn.cso.ie/static/data/ReleaseCalendar.json"
TARGET_SECTORS = {"Economy", "Labour Market and Earnings"}
DAYS_AHEAD = 8
OUTPUT_FILE = "cso_releases.ics"


def fetch_releases():
    with urllib.request.urlopen(CALENDAR_JSON_URL) as response:
        data = json.loads(response.read().decode())
    return data["releases"]


def parse_release_date(date_str):
    """Parse DD/MM/YYYY into a date object."""
    return datetime.strptime(date_str, "%d/%m/%Y").date()


def ical_escape(text):
    """Escape special characters for iCal text fields."""
    return (
        text.replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n")
    )


def fold_line(line):
    """Fold long iCal lines at 75 octets."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    lines = []
    while len(encoded) > 75:
        # Cut at 75 bytes, being careful not to split a multibyte char
        chunk = encoded[:75].decode("utf-8", errors="ignore")
        # Trim back until we get a valid decode
        cut = 75
        while True:
            try:
                chunk = encoded[:cut].decode("utf-8")
                break
            except UnicodeDecodeError:
                cut -= 1
        lines.append(chunk)
        encoded = b" " + encoded[cut:]
    lines.append(encoded.decode("utf-8"))
    return "\r\n".join(lines)


def make_vevent(release):
    release_date = parse_release_date(release["releasedate"])
    title = release["title"]
    ref_period = release.get("refperiod", "")
    sector = release.get("sector", "")
    subsector = release.get("subsector", "")
    status = release.get("status", "")
    comment = release.get("comment", "")

    summary = title
    if ref_period:
        summary += f" ({ref_period})"

    description_parts = [f"Sector: {sector}"]
    if subsector:
        description_parts.append(f"Subsector: {subsector}")
    if status:
        description_parts.append(f"Status: {status}")
    if comment:
        description_parts.append(f"Note: {comment}")
    description_parts.append(f"Source: https://www.cso.ie/en/csolatestnews/releasecalendar/")
    description = "\\n".join(description_parts)

    dtstart = release_date.strftime("%Y%m%d")
    # All-day event: DTEND is the next day
    dtend = (release_date + timedelta(days=1)).strftime("%Y%m%d")
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cso-{release.get('dateindex', title + dtstart)}"))

    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART;VALUE=DATE:{dtstart}",
        f"DTEND;VALUE=DATE:{dtend}",
        f"SUMMARY:{ical_escape(summary)}",
        f"DESCRIPTION:{ical_escape(description)}",
        f"CATEGORIES:{ical_escape(sector)}",
        "STATUS:CONFIRMED",
        "TRANSP:TRANSPARENT",
        "END:VEVENT",
    ]
    return lines


def main():
    today = datetime.now(timezone.utc).date()
    cutoff = today + timedelta(days=DAYS_AHEAD)

    print(f"Fetching CSO release calendar...", file=sys.stderr)
    releases = fetch_releases()
    print(f"Total releases in feed: {len(releases)}", file=sys.stderr)

    filtered = []
    for r in releases:
        try:
            release_date = parse_release_date(r["releasedate"])
        except (KeyError, ValueError):
            continue
        if not (today <= release_date < cutoff):
            continue
        if r.get("sector") not in TARGET_SECTORS:
            continue
        filtered.append(r)

    print(f"Matched releases ({today} to {cutoff - timedelta(days=1)}): {len(filtered)}", file=sys.stderr)
    for r in filtered:
        print(f"  {r['releasedate']} | {r['sector']} | {r['title']}", file=sys.stderr)

    cal_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CSO Release Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:CSO Releases",
        f"X-WR-CALDESC:Economy and Labour Market releases from CSO Ireland",
    ]

    for release in filtered:
        cal_lines.extend(make_vevent(release))

    cal_lines.append("END:VCALENDAR")

    ical_content = "\r\n".join(fold_line(line) for line in cal_lines) + "\r\n"

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(ical_content)

    print(f"Written {len(filtered)} event(s) to {OUTPUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
