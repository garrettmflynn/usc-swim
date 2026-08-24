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

**What's different this week** — the part that actually changes a decision.
Each posted day is compared against its own weekday's history, that week
excluded from its own baseline. A slot the weekday usually has and this week
doesn't is called out ("Tue 6-8am not posted — usually here 10 of 11 weeks"),
as is an hour that turns up which rarely or never appears. Mid-week edits are
flagged separately: the ordinary rhythm is post on Sunday, leave it alone, so
a Wednesday change means something moved under a plan you already made.

Notifications lead with the delta rather than announcing that something
changed — a message you have to open the app to interpret is barely better
than no message. A new week reads as "New swim week posted"; an edit to a week
already up reads as "Fri: removed 6am-8am, 4pm-6pm".

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

## Knowing what you're looking at

Every moving part stamps itself, because a service worker makes "is this the
current build?" unanswerable by eye — a cached bundle looks exactly like a
fresh one.

  Settings -> Build   running commit vs deployed commit, build times, which
                      tool and commit wrote the data, service-worker state
  docs/version.json   the same facts over HTTP, so a deploy can be confirmed
                      with curl instead of a browser
  latest.json         a `generator` block: tool, version, commit, written_at

When the running commit differs from the deployed one the panel says so and
offers a reload that clears the caches. That distinction matters: a stale
service worker and a stale deploy look identical from the outside and need
opposite fixes.

## On a phone

Built mobile-first and verified at 390 / 360 / 320 CSS pixels: no horizontal
overflow at any of them, tap targets at least 44px, and the heat grid scrolls
inside its own box rather than moving the page.

Pinch- and double-tap-zoom are off. iOS Safari ignores `user-scalable=no` on
purpose, so the gestures are declined in `main.tsx` as well — a fixed-layout
schedule should hold still while you read it. Type is sized for phones instead
of relying on zoom, and OS-level display-size settings still apply.

"Today" always comes from the device clock, never from the data. The check
records the date it ran, so reading the week from it would shift everything by
a day the moment midnight passed and label yesterday "Today".

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

**Email** works for everyone with no per-device setup, and sends through Gmail:

1. Turn on 2-Step Verification on the sending Google account (required before
   App Passwords exist at all): <https://myaccount.google.com/security>
2. Create an App Password named "USC Swim":
   <https://myaccount.google.com/apppasswords> — a 16-character string.
3. Store it, along with the account it belongs to:

       gh secret set SMTP_USER --body "you@gmail.com"
       gh secret set SMTP_PASS   # paste the App Password when prompted

`NOTIFY_EMAIL_TO` (comma-separated), `SMTP_HOST`, `SMTP_PORT` and `SMTP_FROM`
are the remaining secrets. Gmail allows ~500 messages a day; this sends about
one a week.

Use an App Password, never the account password — Google rejects the latter for
SMTP, and an App Password can be revoked on its own without touching the
account.

To check it works without waiting for USC: **Actions → watch → Run workflow**,
tick *Send a test notification*. That sends regardless of change and leaves the
change marker alone, so it won't suppress the next real one.

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

`should_commit.py` gates the commit. Every check rewrites `latest.json`
because `checked_at` moves regardless, so an unqualified `git diff` is always
dirty — left alone that is a commit per run, none of which say anything. The
gate ignores per-check noise and commits when the schedule content, the
history or the stats actually differ, plus once a day so the "last checked"
stamp doesn't look abandoned.

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
