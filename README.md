# commit-rate-metric

Re-derives the "commits per workday" metric (baseline vs. current) straight
from git commit logs — the same underlying source used for the metric
template submitted to management.

## Quick start

```bash
python3 commit_rate.py \
  --repos-file repos.txt \
  --author hlarsson@unity.edu --author unity-hallie \
  --range baseline:2024-02-19:2024-12-23 \
  --range current:2026-01-05:2026-08-27
```

Prints the filled METRIC TEMPLATE, e.g.:

```
METRIC TEMPLATE (repeat for up to 3)
Task or output: Commits to UEU repositories from my account
No-AI baseline: 2.2 commits per workday (2024)
Expected outcome with Claude: 13.2 commits per workday (2026, current — measured, not projected)
Where this number comes from: git commit logs across 15 repositories ...
```

## Two-week rolling check

```bash
python3 commit_rate.py --repos-file repos.txt \
  --author hlarsson@unity.edu --author unity-hallie --since 2w --detail
```

## Detailed output

Add `--detail` to any invocation for a full breakdown: commits and workdays
per range, three ways of averaging (mean / median / geomean-of-active-weeks
— see the docstring in `commit_rate.py` for when each is the right tool),
and a per-repository commit count.

## First run

The first run clones any `owner/name` entries in `repos.txt` that aren't
already present locally (into `~/.cache/commit-rate-metric/repos` by
default — override with `--clone-dir`). Subsequent runs reuse the clones;
re-run `git pull` in them yourself to pick up new commits, or delete the
cache dir to force a fresh clone.

## Why "mean commits/workday" and not something fancier

See the docstring at the top of `commit_rate.py`. Short version: it's the
one number that doesn't depend on picking which days count as "active,"
so two different people re-running this script against the same repos
get the same answer.
