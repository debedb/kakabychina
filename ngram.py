#!/usr/bin/env python3
"""Ngram viewer for fast-moving media: phrase frequency over time.

Sources:
  news    GDELT DOC 2.0 -- worldwide online news, 2017-01-01..now, no key needed.
          Value is percent of the articles GDELT monitored in that interval that
          matched. Already normalized, so outlets publishing more do not dominate.
  tv      GDELT TV 2.0 -- US TV news, 2009-07-02..2024-10-31, no key.
          Value is percent of monitored airtime (15-second caption clips),
          averaged across eleven stations: six cable networks (CNN, FOX News,
          MSNBC, CNBC, FOX Business, Bloomberg) plus the five major broadcast
          networks as their San Francisco affiliates (ABC/KGO, CBS/KPIX,
          NBC/KNTV, FOX/KTVU, PBS/KQED). Reaches seven years further back than
          news, but the archive stops in late 2024.
          The panel GROWS over time -- 4 stations in 2009, 9 from mid-2010, all
          11 from end-2013 -- so a station only enters the mean once GDELT began
          indexing it. GDELT reports a flat 0 beforehand, which is
          indistinguishable from "on air, never said it"; averaging those in
          would depress the early years.
          Not included, and why: C-SPAN (gavel-to-gavel proceedings would swamp
          legislative phrasing); BBC/Al Jazeera/DW/RT (market:"International",
          not US); NPR (GDELT publishes no radio API at all). Only San Francisco
          has affiliates running to the end of the archive -- Washington DC dies
          2013-2019, Philadelphia 2018, Chicago 2015, and New York and Los
          Angeles are not in the archive at all.
  bluesky app.bsky.feed.searchPosts -- raw matching-post counts per interval.
          NOT normalized (the API exposes no denominator). Needs BSKY_HANDLE and
          BSKY_APP_PASSWORD in the environment.

news and tv are not interchangeable: percent-of-articles and percent-of-airtime
have different denominators, and over the months they share the same phrase runs
about 6.5x hotter in news at r=0.69. Plot them separately.

Phrases are matched exactly. A bare multi-word phrase gets quoted for you; a
phrase already containing " ( or : is passed through untouched, so full source
syntax works:

  ./ngram.py '"no evidence" (domain:reuters.com OR domain:apnews.com)'
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta

# ponytail: GDELT serves its throttle page to urllib's default User-Agent no
# matter how slowly you poll; a browser UA gets 200 on the same query.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_TV_URL = "https://api.gdeltproject.org/api/v2/tv/tv"
BSKY_URL = "https://bsky.social/xrpc"
GDELT_EPOCH = date(2017, 1, 1)
TV_EPOCH = date(2009, 7, 2)     # the API refuses anything earlier
TV_LAST = date(2024, 10, 31)    # archive stops here
BLOCKS = " .:-=+*#%@"


def fetch(url, headers=None, data=None):
    req = urllib.request.Request(url, data=data,
                                 headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8", "replace")


def as_query(phrase):
    if any(c in phrase for c in '"(:'):
        return phrase
    retval = '"%s"' % phrase if " " in phrase else phrase
    return retval


def first_series(timeline):
    """DOC returns exactly one series."""
    retval = timeline[0]["data"] if timeline else []
    return retval


# `label` is what the API sends back, `since` is when GDELT began indexing that
# station -- verified against two unrelated words, so these are properties of the
# station rather than of whatever you searched for.
STATIONS = [
    ("CNN", "CNN", "2009-07"),
    ("FOXNEWS", "FOX News", "2009-07"),
    ("MSNBC", "MSNBC", "2009-07"),
    ("CNBC", "CNBC", "2009-07"),
    ("FBC", "FOX Business", "2012-08"),
    ("BLOOMBERG", "Bloomberg", "2013-12"),
    ("KGO", "ABC - San Francisco (KGO)", "2010-07"),
    ("KPIX", "CBS - San Francisco (KPIX)", "2010-07"),
    ("KNTV", "NBC - San Francisco (KNTV)", "2010-07"),
    ("KTVU", "FOX - San Francisco (KTVU)", "2010-07"),
    ("KQED", "PBS - San Francisco (KQED)", "2010-07"),
]
STATION_SINCE = {label: since for _, label, since in STATIONS}
STATION_QUERY = "(%s)" % " OR ".join("station:%s" % sid for sid, _, _ in STATIONS)


def mean_across_stations(timeline):
    """TV returns one series per station; the line is their mean.

    A station joins the mean only once GDELT began indexing it. Before that the
    API reports a flat 0, indistinguishable from a station that was on air and
    never said the phrase, and averaging those zeros in would drag the early
    years down. The panel therefore grows: 4 stations in 2009, 9 from mid-2010,
    all 11 from end-2013.

    Being a mean, it also hides disagreement between stations: a phrase
    saturating one network and absent from the rest reads as a middle value.
    """
    totals = defaultdict(lambda: [0.0, 0])
    for station in timeline:
        since = STATION_SINCE.get(station["series"], "0000-00")
        for point in station["data"]:
            if "%s-%s" % (point["date"][:4], point["date"][4:6]) < since:
                continue
            totals[point["date"]][0] += point["value"]
            totals[point["date"]][1] += 1
    retval = [{"date": stamp, "value": total / n}
              for stamp, (total, n) in sorted(totals.items()) if n]
    return retval


def gdelt_series(url, query, since, until, collapse, tries=10):
    """[(date, percent)] from a GDELT timelinevol endpoint."""
    params = urllib.parse.urlencode({
        "query": query,
        "mode": "timelinevol",
        "format": "json",
        "startdatetime": since.strftime("%Y%m%d000000"),
        "enddatetime": until.strftime("%Y%m%d000000"),
    })
    for attempt in range(tries):
        try:
            body = fetch("%s?%s" % (url, params))
        except urllib.error.HTTPError as exc:
            # ponytail: GDELT's 429 is stochastic, not a steady quota -- the same
            # query alternates 429/200 within a minute, so just keep asking.
            # Observed: 4-6 refusals in a row is normal before a 200.
            if exc.code != 429:
                raise
            time.sleep(min(30, 5 * 2 ** attempt))
            continue
        # A rejected query comes back as HTTP 200 carrying a plain-text complaint
        # rather than JSON, so report that text instead of a decode traceback.
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise SystemExit(body.strip()[:200] or "GDELT sent an empty reply")
        retval = [(datetime.strptime(p["date"], "%Y%m%dT%H%M%SZ").date(), p["value"])
                  for p in collapse(payload.get("timeline", []))]
        return retval
    raise SystemExit("GDELT throttled after %d tries: %s" % (tries, query))


def news_series(query, since, until):
    retval = gdelt_series(GDELT_URL, query, since, until, first_series)
    return retval


def tv_series(query, since, until):
    retval = gdelt_series(GDELT_TV_URL, "%s %s" % (query, STATION_QUERY),
                          since, until, mean_across_stations)
    return retval


def bluesky_series(query, since, until, max_pages=50):
    """[(date, matching_post_count)] from Bluesky. Raw counts, no denominator."""
    handle = os.environ.get("BSKY_HANDLE")
    password = os.environ.get("BSKY_APP_PASSWORD")
    if not (handle and password):
        raise SystemExit("--source bluesky needs BSKY_HANDLE and BSKY_APP_PASSWORD "
                         "(an app password from Settings > App Passwords)")
    session = json.loads(fetch(
        "%s/com.atproto.server.createSession" % BSKY_URL,
        {"Content-Type": "application/json"},
        json.dumps({"identifier": handle, "password": password}).encode()))
    auth = {"Authorization": "Bearer %s" % session["accessJwt"]}

    counts = defaultdict(int)
    cursor, pages = None, 0
    while pages < max_pages:
        params = {"q": query, "limit": 100, "sort": "latest",
                  "since": since.isoformat(), "until": until.isoformat()}
        if cursor:
            params["cursor"] = cursor
        page = json.loads(fetch(
            "%s/app.bsky.feed.searchPosts?%s" % (BSKY_URL, urllib.parse.urlencode(params)),
            auth))
        posts = page.get("posts", [])
        for post in posts:
            stamp = post.get("record", {}).get("createdAt") or post["indexedAt"]
            counts[datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()] += 1
        cursor = page.get("cursor")
        pages += 1
        if not cursor or not posts:
            break
        time.sleep(0.3)
    if cursor and pages >= max_pages:
        print("warning: %s truncated at %d posts -- narrow the date range"
              % (query, max_pages * 100), file=sys.stderr)
    retval = sorted(counts.items())
    return retval


def bucket(series, size, how):
    grouped = defaultdict(list)
    for day, value in series:
        if size == "day":
            key = day
        elif size == "week":
            key = day - timedelta(days=day.weekday())
        else:
            key = day.replace(day=1)
        grouped[key].append(value)
    agg = (lambda xs: sum(xs) / len(xs)) if how == "mean" else sum
    retval = [(key, agg(grouped[key])) for key in sorted(grouped)]
    return retval


def spark(values):
    top = max(values) or 1
    retval = "".join(BLOCKS[round(v / top * (len(BLOCKS) - 1))] for v in values)
    return retval


def report(phrase, points, unit, width):
    if not points:
        print("%s: no data\n" % phrase)
        return
    shown = points[-width:]
    values = [v for _, v in shown]
    peak_day, peak = max(shown, key=lambda kv: kv[1])
    print("%s  [%s]" % (phrase, unit))
    print("  %s .. %s" % (shown[0][0], shown[-1][0]))
    print("  %s" % spark(values))
    print("  mean %.4g   peak %.4g on %s" % (sum(values) / len(values), peak, peak_day))
    if len(points) > width:
        print("  (showing last %d of %d buckets)" % (width, len(points)))
    print()


def self_test():
    assert as_query("nuclear disarmament") == '"nuclear disarmament"'
    assert as_query("BLM") == "BLM"
    assert as_query('"no evidence" AND (domain:cnn.com)') == '"no evidence" AND (domain:cnn.com)'

    series = [(date(2026, 1, 5), 2.0), (date(2026, 1, 6), 4.0), (date(2026, 2, 3), 9.0)]
    assert bucket(series, "day", "mean") == series
    assert bucket(series, "week", "mean") == [(date(2026, 1, 5), 3.0), (date(2026, 2, 2), 9.0)]
    assert bucket(series, "month", "sum") == [(date(2026, 1, 1), 6.0), (date(2026, 2, 1), 9.0)]

    assert first_series([]) == []
    assert first_series([{"data": [{"date": "x", "value": 1.0}]}]) == [{"date": "x", "value": 1.0}]

    # Two stations, one date each way: the line is their mean, and a date only
    # one station carries is that station's own value.
    timeline = [
        {"series": "CNN", "data": [{"date": "20200101T120000Z", "value": 1.0},
                                   {"date": "20200201T120000Z", "value": 4.0}]},
        {"series": "MSNBC", "data": [{"date": "20200101T120000Z", "value": 3.0}]},
    ]
    assert mean_across_stations(timeline) == [{"date": "20200101T120000Z", "value": 2.0},
                                              {"date": "20200201T120000Z", "value": 4.0}]
    assert mean_across_stations([]) == []

    # Bloomberg's zeros before 2013-12 must not dilute CNN, or a 2.0 becomes 1.0.
    early = [
        {"series": "CNN", "data": [{"date": "20100101T120000Z", "value": 2.0},
                                   {"date": "20140101T120000Z", "value": 2.0}]},
        {"series": "Bloomberg", "data": [{"date": "20100101T120000Z", "value": 0.0},
                                         {"date": "20140101T120000Z", "value": 0.0}]},
    ]
    assert mean_across_stations(early) == [{"date": "20100101T120000Z", "value": 2.0},
                                           {"date": "20140101T120000Z", "value": 1.0}]

    low, mid, high = spark([0, 5, 10])
    assert (low, high) == (BLOCKS[0], BLOCKS[-1])
    assert BLOCKS.index(low) < BLOCKS.index(mid) < BLOCKS.index(high)
    assert spark([0, 0, 0]) == BLOCKS[0] * 3
    print("ok")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("phrases", nargs="*", help="phrase(s) to trend")
    parser.add_argument("--source", choices=["news", "tv", "bluesky"], default="news")
    parser.add_argument("--since", help="YYYY-MM-DD (default: 1 year back)")
    parser.add_argument("--until", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--bucket", choices=["day", "week", "month"], default="week")
    parser.add_argument("--csv", action="store_true", help="date,phrase,value to stdout")
    parser.add_argument("--width", type=int, default=100, help="chart buckets to show")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if not args.phrases:
        parser.error("give at least one phrase")

    until = date.fromisoformat(args.until) if args.until else date.today()
    since = date.fromisoformat(args.since) if args.since else until - timedelta(days=365)

    if args.source == "news":
        fetch_series, how, unit = news_series, "mean", "% of monitored articles"
        first, last = GDELT_EPOCH, None
    elif args.source == "tv":
        fetch_series, how, unit = tv_series, "mean", "% of monitored airtime"
        first, last = TV_EPOCH, TV_LAST
    else:
        fetch_series, how, unit = bluesky_series, "sum", "matching posts"
        first, last = None, None

    if first and since < first:
        print("note: %s coverage starts %s, clamping --since" % (args.source, first),
              file=sys.stderr)
        since = first
    if last and until > last:
        print("note: %s coverage ends %s, clamping --until" % (args.source, last),
              file=sys.stderr)
        until = last
    if since > until:
        raise SystemExit("%s covers %s..%s -- nothing in the range you asked for"
                         % (args.source, first, last))

    if args.csv:
        print("date,phrase,value")
    for i, phrase in enumerate(args.phrases):
        if i and args.source in ("news", "tv"):
            time.sleep(5)  # GDELT asks for one request per 5s
        points = bucket(fetch_series(as_query(phrase), since, until), args.bucket, how)
        if args.csv:
            for day, value in points:
                print('%s,"%s",%g' % (day, phrase.replace('"', '""'), value))
        else:
            report(phrase, points, unit, args.width)


if __name__ == "__main__":
    main()
