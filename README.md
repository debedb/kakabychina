# kakabychina

Ngram viewer for fast-moving media: how often a phrase shows up in worldwide
online news, over time.

Google Books Ngrams stops at books and ends in 2019. This does the same thing
for news, through today, via the
[GDELT DOC 2.0 API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/).

Values are **share of monitored coverage** — the percent of everything GDELT
watched in that interval that matched — so outlets that simply publish more
don't dominate.

## Web

`index.html` is the whole thing: one file, no build, no dependencies, no API
key. It calls GDELT straight from the browser.

```
python3 -m http.server 8931   # then open http://localhost:8931/
```

## CLI

```
./ngram.py 'quiet quitting'
./ngram.py 'nuclear disarmament' 'arms control' --since 2017-01-01 --bucket month
./ngram.py 'quiet quitting' --csv > data.csv
./ngram.py --self-test
```

Also speaks Bluesky (`--source bluesky`, raw post counts, needs `BSKY_HANDLE`
and `BSKY_APP_PASSWORD`). Those counts are **not** normalized — the API exposes
no denominator.

## Query syntax

Passed straight through to GDELT, so source filters work:

```
./ngram.py '"no evidence" (domain:reuters.com OR domain:apnews.com)'
```

A phrase already containing `"`, `(` or `:` is sent verbatim. Anything else
gets quoted for you, so multi-word phrases match exactly.

## Limits

- **Coverage starts 2017-01-01.** That's GDELT DOC 2.0's own floor, not a
  setting. Earlier dates are clamped.
- **GDELT throttles hard and stochastically** — the same query alternates
  429/200 within a minute. Both the page and the CLI just keep retrying.
  From a browser the 429 has no CORS header, so it surfaces as an opaque
  fetch failure rather than a readable status.

See `docs/examples/` for sample output.
