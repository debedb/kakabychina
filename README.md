# kakabychina

Ngram viewer for fast-moving media: how often a phrase shows up in the news,
over time.

Google Books Ngrams stops at books and ends in 2019. This does the same thing
for news, using [GDELT](https://www.gdeltproject.org/) — online news through
today, and US television back to 2009.

## Web

`index.html` is the whole thing: one file, no build, no dependencies, no API
key. It calls GDELT straight from the browser.

```
python3 -m http.server 8931   # then open http://localhost:8931/
```

## CLI

```
./ngram.py 'quiet quitting'
./ngram.py 'nuclear disarmament' 'arms control' --bucket month
./ngram.py 'no evidence' --source tv --since 2010-01-01
./ngram.py 'quiet quitting' --csv > data.csv
./ngram.py --self-test
```

Also speaks Bluesky (`--source bluesky`, needs `BSKY_HANDLE` and
`BSKY_APP_PASSWORD`). Those are raw post counts, **not** normalized — that API
exposes no denominator.

## The two sources

| | Online news | TV |
|---|---|---|
| Covers | 2017-01-01 → today | 2009-07-02 → 2024-10-31 |
| Reach | Worldwide | 9 US national networks |
| Y axis | % of monitored **articles** | % of monitored **airtime** |

**Online news** — the percent of the articles GDELT monitored worldwide in that
interval which contained your phrase. Read 1.1% as roughly one article in ninety.

**TV** — GDELT cuts each broadcast into 15-second clips and counts the ones whose
captions contain your phrase. The line is that percentage averaged across the
stations that were on air at the time. (CNN alone contributes about 130,000 clips
a month.)

Both are shares rather than counts, so an outlet or network that simply produces
more does not dominate.

### Which stations the TV chart covers

Eleven — six cable networks, plus the five major broadcast networks as their San
Francisco affiliates. The year is when GDELT began indexing each one:

| Cable | Since | | Broadcast (SF affiliate) | Since |
|---|---|---|---|---|
| CNN | 2009-07 | | ABC — KGO | 2010-07 |
| FOX News | 2009-07 | | CBS — KPIX | 2010-07 |
| MSNBC | 2009-07 | | NBC — KNTV | 2010-07 |
| CNBC | 2009-07 | | FOX — KTVU | 2010-07 |
| FOX Business | 2012-08 | | PBS — KQED | 2010-07 |
| Bloomberg | 2013-12 | | | |

**The panel grows over time**: 4 stations in 2009, 9 from mid-2010, all 11 from
end-2013. A station enters the mean only once it exists. GDELT reports a flat `0`
for a station before it was indexed — indistinguishable from one that was on air
and never said your phrase — and averaging those zeros in understates the early
years badly. For "climate change" in December 2009, including them gives 0.34%
where the four stations actually on air averaged 0.94%.

**The broadcast networks are one city's affiliates, not national feeds.** GDELT
has no national ABC/CBS/NBC/PBS; it indexes them station by station, and San
Francisco is the only market whose affiliates run to the end of the archive.
Washington DC's stop between 2013 and 2019, Philadelphia's in 2018, Chicago's in
2015, and **New York and Los Angeles are not in the archive at all**. KGO carries
ABC's national programming plus Bay Area local news, so treat it as a stand-in for
ABC, not as ABC — local stories carry a California accent.

**Deliberately excluded:** C-SPAN 1–3 (gavel-to-gavel proceedings would swamp
legislative phrasing), and BBC News / Al Jazeera / Deutsche Welle / Russia Today
(international, not US). **NPR is absent because GDELT publishes no radio API at
all** — `/api/v2/radio` 404s. The archive is television captions; there is no
radio equivalent to query.

## Why two charts and not one

They are plotted separately, on their own axes, and that is deliberate.

Measured over the 94 months where both have data, the same phrase runs about
**6.5× hotter** on the news chart than the TV chart, and the two move together
only loosely (r = 0.69). In January 2023, "climate change" sat near its *high* in
online news and near its *low* on television.

A shared axis would flatten TV into a line along the floor. Two axes on one chart
would be worse: any pair of scales can manufacture whatever agreement you want to
see. A percent of articles and a percent of airtime are not the same quantity,
and the ratio between them means nothing.

So each source gets its own chart, its own axis, and its own date range.

## Date ranges

Ask for a window a source does not cover and it quietly narrows to what exists —
the line under each chart title always states what you actually got. Ask for a
window a source misses entirely (say, 2010–2015 on the news chart) and that chart
says so while the other still plots. The CLI clamps the same way and prints a
note to stderr.

TV reaches seven years further back than online news, but its archive stops in
late 2024, so it cannot tell you about the present. Neither source alone spans
the whole period.

## Searching

Multi-word phrases are matched exactly. Query syntax passes straight through to
GDELT, so source filters work:

```
./ngram.py '"no evidence" (domain:reuters.com OR domain:apnews.com)'
```

A line already containing `"`, `(` or `:` is sent verbatim. Anything else gets
quoted for you.

## Known annoyances

GDELT throttles aggressively and will refuse several requests in a row before
answering — four to six refusals is normal. Both the page and the CLI wait and
retry, which is why plotting several phrases takes a while. From a browser the
throttle response carries no CORS header, so it arrives as an opaque failure
rather than a readable 429; the page treats both the same way.

See `docs/examples/` for sample output.

## License

MIT
