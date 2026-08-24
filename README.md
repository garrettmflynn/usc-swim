# USC Swim

Rec swim hours at the Uytengsu Aquatics Center — and, when USC hasn't posted
next week yet, what that weekday usually looks like.

It exists because the schedule goes up late and irregularly: they post on a
Sunday or Monday, and until they do there is nothing to plan against. So this
watches the page, records every version, and fills the gap with history.

    app/         the PWA (React + Vite). Installable, works offline.
    scrape.py    fetch -> extract -> parse -> diff -> write
    backfill.py  recover pre-redesign schedules from the Wayback Machine
    notify.py    email + web push, only when the content actually changes
    docs/        what GitHub Pages serves: the built app plus the dataset
    docs/data/   latest.json, history.json, stats.json
    tests/       fixtures are real captures; each one broke something once

`docs/data/history.json` is the dataset. Everything else is derived from it,
and the app reads it at runtime — so the hourly watcher never rebuilds the app.

## The one design rule

**Posted and expected are never blended.** A day either carries hours USC
actually published, or an expectation drawn from history — and it always says
which. "They said 6am" and "6am is usually there" support very different
decisions, and a dashboard that quietly merges them is worse than no dashboard.

The same rule runs deeper than the UI. A row the page never mentioned is
`closed: null`, not `false`; the pool being unlisted is not a statement that it
was shut. Anything the parser can't account for is reported rather than dropped.

## What it tells you

**The week ahead** — seven days, posted where posted, expected where not.

**Patterns** — how often each weekday and hour has actually been swimmable.
Counts are shown alongside rates, because a denominator of two makes 100%
meaningless. As of writing: weekday mornings and lunch run 66–91%, Saturday is
the weak day at 46%, and nothing has ever opened 8–11am or after 6pm.

**Pool rhythm** — the two pools take turns rather than running together. Across
every day on record they are never open at the same moment: Comp covers 12–2pm,
Dive covers 6–8am, 11am–12pm and 4–6pm. So "is anything open" is the question.

**Parse health** — whether the scraper still understands the page, kept
deliberately separate from whether USC's own data is wrong. A typo'd date is
their mistake and doesn't mean the parser needs fixing; unrecognised lines do.
A check that yields no rows at all exits non-zero and fails the workflow.

## Setup

1. Push the repo. Settings → Pages → Deploy from a branch, `main`, `/docs`.
2. Settings → Actions → General → Workflow permissions: **Read and write**.
3. Put a real contact address in `CONTACT` at the top of `scrape.py`. It goes
   in the User-Agent, which is the polite thing to do and costs nothing.
4. Actions → watch → Run workflow, to seed the first snapshot.

Local: `./run.sh`, or `cd app && npm install && npm run dev`.

### Backfill

    python backfill.py --dry-run    # parse and report, write nothing
    python backfill.py              # merge into history.json

Recovers ~12 weeks from October 2024 onward. Captures are roughly monthly, so
these are marked `origin: "wayback"` and excluded from the post-lag median —
a capture time is not a post time.

Roughly five more weeks exist in March–July 2024 in a third page format, which
would need another parser. Common Crawl was checked and adds nothing new.

### Notifications

Both channels are optional and skipped quietly when unconfigured.

**Email** works for everyone with no per-device setup. Set `NOTIFY_EMAIL_TO`
and `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` as repository secrets.

**Web push** is nicer but has to be enrolled once per device, because the site
is static and there is no server to register subscriptions:

1. `python bin-keygen.py` — generates a VAPID keypair.
2. Public half → repository **variable** `VAPID_PUBLIC_KEY` (it ships in the
   bundle, which is fine). Private half → repository **secret**
   `VAPID_PRIVATE_KEY`. Also set `VAPID_SUBJECT` to `mailto:you@…`.
3. Open the app, Settings → Turn on notifications, then **Copy subscription**.
4. Paste it into the `PUSH_SUBSCRIPTIONS` secret — a JSON array, one entry per
   device.

On iOS this only works once the app is on the home screen; iOS won't grant
notification permission to a browser tab. If enrolling ever needs to be
self-serve, a small Cloudflare Worker holding subscriptions is the upgrade.

## Cadence

The page changes about once a week, and they post on Sunday or Monday — ten of
the fourteen recorded updates landed within a day of the week they cover. So
the watcher runs hourly through that window and every six hours otherwise,
rather than hourly around the clock. It fires at `:37`; the top of the hour is
the most contended slot on GitHub's scheduler and gets delayed or dropped.

Conditional GETs mean an unchanged page costs a 304 and commits nothing.
Scheduled workflows are disabled after 60 days of repository inactivity.

## If the parser breaks

Every snapshot keeps `raw_block`, the section's HTML as fetched. When they
restructure the page, fix the parser and replay history rather than losing it.
If the `Rec Swim Hours` heading disappears entirely the run raises `LookupError`
and the workflow fails loudly, which is correct.

Run `pytest tests/ -q` first — it's fixture-only and needs no network, and the
watcher runs it before the fetch so a broken parser can't append a bogus
snapshot to the dataset.

## Manners

One conditional GET per check, with a contact string in the User-Agent, on a
public page with no robots restriction on this path. Backfill requests are
paced and cached on disk, because captures are immutable and the archive is a
donation. Don't raise the frequency; they don't update more than once a week.
