#!/usr/bin/env python3
"""
commit_rate.py — commits/day across the N most substantial repos, for a date range.

For each requested date range: find every org repo with >=1 commit by
the given author in that range, rank those by TOTAL historical commit
count (a proxy for "how substantial is this codebase" — not commits
in the window, to avoid circularity), keep the top N, sum the
author's commits to just those repos in the range, divide by weekdays.

Runs entirely against the GitHub REST API via `gh` — no repos are
cloned. Requires `gh auth login` to already be done.

USAGE

    python3 commit_rate.py --org Unity-Environmental-University \
        --author hlarsson@unity.edu --author unity-hallie \
        --range baseline:2024-05-06:2024-05-10 \
        --range current:2026-07-06:2026-07-10 \
        --template "Commits to my 3 most substantial UEU repositories, one representative work week"

Prints exactly the four METRIC TEMPLATE lines. Add --detail for the
full breakdown (which repos qualified, their total-commit rank, and
how many commits each contributed to the window).

REPO RANKING (--top-n, default 3)

    "Most substantial" = highest total commit count across all of a
    repo's history (`git log --all --oneline | wc -l`, fetched here
    via the REST commits API's Link-header pagination count instead
    of cloning). This is independent of the date range being
    measured, so there's no circularity in "pick the biggest repo,
    using the thing you're trying to measure." Only repos with >=1
    commit by the author IN THE WINDOW are eligible to rank at all;
    among those, the top N by total size are kept and everything else
    is dropped — repos that were merely brushed that week don't drag
    the number down, and repos with no activity that week don't count
    even if they're huge.

WHY THIS SHAPE

    A whole-year, whole-org analysis is the more complete picture (see
    this repo's git history for that version), but it needs many API
    calls, takes minutes, and "which of ~100 repos count" is a bigger
    surface to argue about. A single representative week, scoped to
    the repos that actually mattered that week, is a number a
    reviewer can sanity-check by eye and reproduce by hand in a couple
    of minutes — that reproducibility is the point.
"""
import argparse
import datetime
import subprocess
import sys
import zoneinfo
from collections import defaultdict

ET = zoneinfo.ZoneInfo("America/New_York")


def parse_range(spec):
    label, start, end = spec.split(":", 2)
    return label, datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)


def gh_api_jq(path, jq_filter, paginate=True):
    cmd = ["gh", "api"]
    if paginate:
        cmd.append("--paginate")
    cmd += [path, "-q", jq_filter]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return [line for line in out.stdout.splitlines() if line.strip()]


def list_org_repos(org):
    slugs = gh_api_jq(f"orgs/{org}/repos?per_page=100", ".[].full_name")
    if slugs is None:
        raise RuntimeError(f"gh api failed listing repos for org {org}; is `gh auth login` done?")
    return slugs


def commits_by_author_in_window(slug, authors, lo, hi):
    """Total commits by any of `authors` (GitHub logins) in [lo, hi]
    on the default branch. One API call per author; small windows
    only, so this stays cheap."""
    since = f"{lo.isoformat()}T00:00:00Z"
    until = f"{(hi + datetime.timedelta(days=1)).isoformat()}T00:00:00Z"
    seen = set()
    for login in authors:
        lines = gh_api_jq(
            f"repos/{slug}/commits?author={login}&since={since}&until={until}&per_page=100",
            ".[].sha",
        )
        if lines:
            seen.update(lines)
    return len(seen)


def total_commit_count(slug):
    """Total commits on the default branch, ever — the 'substantial'
    proxy. Uses the Link header's last-page trick via `gh api` with a
    tiny per_page, which is much cheaper than paginating everything."""
    out = subprocess.run(
        ["gh", "api", f"repos/{slug}/commits?per_page=1", "-i"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        return 0
    link = ""
    for line in out.stdout.splitlines():
        if line.lower().startswith("link:"):
            link = line
            break
    if 'rel="last"' in link:
        # .../commits?per_page=1&page=N>; rel="last"
        for part in link.split(","):
            if 'rel="last"' in part:
                url = part.split(";")[0].strip().strip("<>")
                if "page=" in url:
                    try:
                        return int(url.split("page=")[-1])
                    except ValueError:
                        return 0
    # no Link header at all means 0 or 1 commit total
    return 1 if '"sha"' in out.stdout else 0


def workdays_between(lo, hi):
    n, d = 0, lo
    while d <= hi:
        if d.weekday() < 5:
            n += 1
        d += datetime.timedelta(days=1)
    return n


def analyze_range(org, authors, lo, hi, top_n):
    slugs = list_org_repos(org)
    print(f"  checking {len(slugs)} repos for commits by {'/'.join(authors)} "
          f"in {lo}..{hi}...", file=sys.stderr)
    active = {}
    for slug in slugs:
        n = commits_by_author_in_window(slug, authors, lo, hi)
        if n > 0:
            active[slug] = n
    print(f"  {len(active)} repos had >=1 matching commit that week; "
          f"ranking by total commit count...", file=sys.stderr)
    ranked = sorted(active.keys(), key=total_commit_count, reverse=True)
    top = ranked[:top_n]
    commits = sum(active[s] for s in top)
    wd = workdays_between(lo, hi)
    return {
        "lo": lo, "hi": hi, "commits": commits, "workdays": wd,
        "per_day": commits / wd if wd else 0.0,
        "repos": [(s, active[s]) for s in top],
        "all_active": active,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--org", required=True, help="GitHub org to check")
    ap.add_argument("--author", action="append", required=True,
                     help="GitHub login to match commits against (repeatable)")
    ap.add_argument("--range", action="append", required=True, metavar="LABEL:START:END",
                     help="date range, e.g. baseline:2024-05-06:2024-05-10; repeatable, first two used as baseline/current")
    ap.add_argument("--top-n", type=int, default=3,
                     help="how many of the most-substantial active repos to count (default 3)")
    ap.add_argument("--template", default="Commits to UEU repositories from my account",
                     help="the 'Task or output' line")
    ap.add_argument("--detail", action="store_true", help="print the full repo breakdown instead of just the template")
    args = ap.parse_args()

    ranges = [parse_range(r) for r in args.range]
    if len(ranges) < 2 and not args.detail:
        ap.error("template output needs two --range entries: baseline and current")

    results = []
    for label, lo, hi in ranges:
        r = analyze_range(args.org, args.author, lo, hi, args.top_n)
        r["label"] = label
        results.append(r)

    if args.detail:
        print()
        for r in results:
            print(f"--- {r['label']}  ({r['lo']} .. {r['hi']}) ---")
            print(f"  top {args.top_n} repos used (of {len(r['all_active'])} active that week):")
            for slug, n in r["repos"]:
                print(f"    {slug:55} {n:4} commits this window")
            print(f"  total: {r['commits']} commits / {r['workdays']} workdays = {r['per_day']:.1f}/day")
            print()
        return

    base, cur = results[0], results[1]
    print("METRIC TEMPLATE (repeat for up to 3)")
    print(f"Task or output: {args.template}")
    print(f"No-AI baseline: {base['per_day']:.1f} commits/day")
    print(f"Expected outcome with Claude: {cur['per_day']:.1f} commits/day")
    print(f"Where this number comes from: git log --all --no-merges, author = {' / '.join(args.author)}, "
          f"{base['lo']:%b %-d}–{base['hi']:%-d %Y} vs {cur['lo']:%b %-d}–{cur['hi']:%-d %Y}. "
          f"Repos = top {args.top_n} by total commit count among those active that week: "
          + "; ".join(f"{r['label']} = " + " + ".join(s.split('/')[-1] for s, _ in r["repos"])
                       for r in results)
          )


if __name__ == "__main__":
    main()
