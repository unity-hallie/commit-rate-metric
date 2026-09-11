#!/usr/bin/env python3
"""
commit_rate.py — re-derive the "commits per workday" metric from git logs.

Computes, for one or more date ranges (e.g. a baseline period and a
current period), the commit rate for a given author across a set of
git repositories. Outputs the exact METRIC TEMPLATE line by default,
or a detailed breakdown with --detail.

USAGE

    # Two-week window ending today, across repos listed in repos.txt:
    python3 commit_rate.py --repos-file repos.txt --author hlarsson@unity.edu \
        --author unity-hallie --since 2w

    # Explicit baseline vs current comparison, template output:
    python3 commit_rate.py --repos-file repos.txt \
        --author hlarsson@unity.edu --author unity-hallie \
        --range baseline:2024-02-19:2024-12-23 \
        --range current:2026-01-05:2026-08-27 \
        --template "Commits to UEU repositories from my account"

    # Same, with full statistical detail (mean/median/geomean, per-repo):
    python3 commit_rate.py --repos-file repos.txt \
        --author hlarsson@unity.edu --author unity-hallie \
        --range baseline:2024-02-19:2024-12-23 \
        --range current:2026-01-05:2026-08-27 \
        --detail

REPOS FILE

    One path (local clone) or "owner/name" (cloned via gh/git if not
    present locally, into --clone-dir) per line. Blank lines and lines
    starting with # are ignored.

NOTES ON STATISTICS

    "Commits per workday" is a ratio (count / 1 day). This script
    reports three ways of averaging that ratio across a period, since
    they are not interchangeable and the right one depends on intent:

      mean    total commits / total workdays in the date range.
              Correct for "aggregate throughput" — invariant to how
              the period is chopped into days or weeks. This is what
              the template field reports by default.

      median  the middle daily count, sorted. Robust to a few binge
              days (e.g. one 1,181-commit month) dominating the
              average — use this if outlier days are a concern.

      geomean-of-active-weeks
              geometric mean of (commits that week / workdays that
              week), computed only over weeks with >=1 commit.
              Geometric mean is the right tool when you care about a
              compounding/multiplicative rate rather than aggregate
              total, and when values span orders of magnitude — but
              it is undefined (or 0) for any day/week with zero
              commits, so it is computed here only over active weeks,
              never over raw daily counts (which are mostly zero on
              weekends and off days).

    For a single management-facing number, `mean` (workdays-based) is
    the most defensible: one denominator, no cherry-picking of which
    days count, reproducible by anyone re-running this script.
"""
import argparse
import datetime
import math
import os
import statistics
import subprocess
import sys
import zoneinfo
from collections import defaultdict

ET = zoneinfo.ZoneInfo("America/New_York")


def parse_range(spec):
    label, start, end = spec.split(":", 2)
    lo = datetime.date.fromisoformat(start)
    hi = datetime.date.fromisoformat(end)
    return label, lo, hi


def resolve_repo(entry, clone_dir):
    """entry is a local path or 'owner/name'. Returns a local path,
    cloning into clone_dir if it's a GitHub slug not already cloned."""
    if os.path.isdir(os.path.join(entry, ".git")):
        return entry
    if "/" in entry and not os.path.isabs(entry) and not entry.startswith("."):
        name = entry.split("/")[-1]
        local = os.path.join(clone_dir, name)
        if os.path.isdir(os.path.join(local, ".git")):
            return local
        os.makedirs(clone_dir, exist_ok=True)
        url = f"https://github.com/{entry}.git"
        print(f"  cloning {entry} -> {local}", file=sys.stderr)
        subprocess.run(["git", "clone", "--quiet", url, local], check=True)
        return local
    raise FileNotFoundError(f"not a git repo and not an owner/name slug: {entry}")


def load_repos_file(path):
    repos = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            repos.append(line)
    return repos


def collect_commits(repo_paths, authors, clone_dir):
    """Returns list of (datetime_ET, repo_label) for every non-merge
    commit by any of `authors`, deduplicated by commit hash across
    all repos (a commit hash is globally unique)."""
    seen = set()
    rows = []
    for entry in repo_paths:
        path = resolve_repo(entry, clone_dir)
        label = os.path.basename(path.rstrip("/"))
        out = subprocess.run(
            ["git", "-C", path, "log", "--all", "--no-merges",
             "--pretty=format:%H\x1f%aI\x1f%ae\x1e"],
            capture_output=True, text=True,
        ).stdout
        for rec in out.split("\x1e"):
            rec = rec.strip("\n")
            if not rec:
                continue
            parts = rec.split("\x1f")
            if len(parts) < 3:
                continue
            h, iso, ae = parts
            if h in seen:
                continue
            ael = ae.lower()
            if not any(a.lower() in ael for a in authors):
                continue
            seen.add(h)
            try:
                dt = datetime.datetime.fromisoformat(iso).astimezone(ET)
            except ValueError:
                continue
            rows.append((dt, label))
    return rows


def workdays_between(lo, hi):
    n = 0
    d = lo
    while d <= hi:
        if d.weekday() < 5:
            n += 1
        d += datetime.timedelta(days=1)
    return n


def analyze_range(rows, lo, hi):
    """rows already filtered to [lo, hi]. Returns a dict of stats."""
    dates = [r[0].date() for r in rows]
    n = len(rows)
    wd = workdays_between(lo, hi)
    mean_per_workday = n / wd if wd else 0.0

    # daily counts (workdays only) for median
    per_day = defaultdict(int)
    for d in dates:
        if d.weekday() < 5:
            per_day[d] += 1
    all_workday_counts = []
    d = lo
    while d <= hi:
        if d.weekday() < 5:
            all_workday_counts.append(per_day.get(d, 0))
        d += datetime.timedelta(days=1)
    median_per_workday = statistics.median(all_workday_counts) if all_workday_counts else 0.0

    # geomean of active weeks: (commits in week / workdays in week)
    week_commits = defaultdict(int)
    week_workdays = defaultdict(int)
    d = lo
    while d <= hi:
        if d.weekday() < 5:
            wk = d.isocalendar()[:2]
            week_workdays[wk] += 1
        d += datetime.timedelta(days=1)
    for dt in dates:
        wk = dt.isocalendar()[:2]
        week_commits[wk] += 1
    active_week_rates = [
        week_commits[wk] / week_workdays[wk]
        for wk in week_workdays
        if week_commits.get(wk, 0) > 0
    ]
    geomean_active_weeks = (
        math.exp(sum(math.log(x) for x in active_week_rates) / len(active_week_rates))
        if active_week_rates else 0.0
    )

    by_repo = defaultdict(int)
    for _, label in rows:
        by_repo[label] += 1

    return {
        "commits": n,
        "workdays": wd,
        "mean_per_workday": mean_per_workday,
        "median_per_workday": median_per_workday,
        "geomean_active_weeks_per_workday": geomean_active_weeks,
        "active_weeks": len(active_week_rates),
        "by_repo": dict(sorted(by_repo.items(), key=lambda kv: -kv[1])),
        "lo": lo, "hi": hi,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repos-file", required=True, help="file listing repos, one per line (local path or owner/name)")
    ap.add_argument("--author", action="append", required=True, help="author match string (email fragment or handle); repeatable")
    ap.add_argument("--range", action="append", metavar="LABEL:START:END",
                     help="a date range to analyze, e.g. baseline:2024-02-19:2024-12-23; repeatable, up to 2 used for the template (baseline + current)")
    ap.add_argument("--since", help="shorthand: analyze the single window from N(d|w) ago to today, e.g. 2w, 14d")
    ap.add_argument("--clone-dir", default=os.path.expanduser("~/.cache/commit-rate-metric/repos"),
                     help="where to clone owner/name repos not found locally")
    ap.add_argument("--template", default="Commits to UEU repositories from my account",
                     help="the 'Task or output' line for template mode")
    ap.add_argument("--detail", action="store_true", help="print full per-range and per-repo breakdown instead of the template")
    args = ap.parse_args()

    ranges = []
    if args.since:
        n = int("".join(c for c in args.since if c.isdigit()))
        unit = args.since[-1]
        days = n * 7 if unit == "w" else n
        hi = datetime.datetime.now(ET).date()
        lo = hi - datetime.timedelta(days=days)
        ranges.append(("window", lo, hi))
    if args.range:
        for spec in args.range:
            ranges.append(parse_range(spec))
    if not ranges:
        ap.error("provide --range (repeatable) or --since")

    repos = load_repos_file(args.repos_file)
    print(f"Loading {len(repos)} repositories...", file=sys.stderr)
    all_rows = collect_commits(repos, args.author, args.clone_dir)
    print(f"{len(all_rows)} total commits by matched authors across all history.", file=sys.stderr)

    results = []
    for label, lo, hi in ranges:
        rows_in_range = [r for r in all_rows if lo <= r[0].date() <= hi]
        stats = analyze_range(rows_in_range, lo, hi)
        stats["label"] = label
        results.append(stats)

    if args.detail:
        print()
        print("=" * 72)
        print("COMMIT RATE — DETAILED OUTPUT")
        print("=" * 72)
        print(f"Authors matched: {', '.join(args.author)}")
        print(f"Repositories:    {len(repos)}")
        for s in results:
            print()
            print(f"--- {s['label']}  ({s['lo']} .. {s['hi']}) ---")
            print(f"  commits:                         {s['commits']}")
            print(f"  workdays in range:                {s['workdays']}")
            print(f"  mean commits/workday:              {s['mean_per_workday']:.2f}")
            print(f"  median commits/workday:            {s['median_per_workday']:.2f}")
            print(f"  geomean commits/workday            {s['geomean_active_weeks_per_workday']:.2f}")
            print(f"    (of {s['active_weeks']} active weeks; excludes zero-commit weeks)")
            print(f"  by repository:")
            for repo, n in s["by_repo"].items():
                print(f"    {repo:28} {n:5}")
        if len(results) >= 2:
            base, cur = results[0], results[-1]
            if base["mean_per_workday"] > 0:
                ratio = cur["mean_per_workday"] / base["mean_per_workday"]
                print()
                print(f"Ratio (mean, {cur['label']} / {base['label']}): {ratio:.1f}x")
    else:
        if len(results) < 2:
            ap.error("template output needs two --range entries: baseline and current")
        base, cur = results[0], results[-1]
        cmd_hint = "git log --all --no-merges --pretty=format:'%H %aI %ae'"
        print("METRIC TEMPLATE (repeat for up to 3)")
        print(f"Task or output: {args.template}")
        print(f"No-AI baseline: {base['mean_per_workday']:.1f} commits per workday ({base['lo'].year})")
        print(f"Expected outcome with Claude: {cur['mean_per_workday']:.1f} commits per workday "
              f"({cur['lo'].year}, current — measured, not projected)")
        print(f"Where this number comes from: git commit logs across {len(repos)} repositories "
              f"(all branches, non-merge commits, author = {' / '.join(args.author)}), e.g. `{cmd_hint}`. "
              f"Rate = total commits ÷ workdays (Mon–Fri) across the full calendar span of each period's data: "
              f"{base['commits']} commits over {base['workdays']} workdays ({base['lo']} to {base['hi']}); "
              f"{cur['commits']} commits over {cur['workdays']} workdays ({cur['lo']} to {cur['hi']}).")


if __name__ == "__main__":
    main()
