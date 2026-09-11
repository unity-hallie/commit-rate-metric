# commit-rate-metric

Commits/day, baseline vs current, for a single representative Mon–Fri
work week — computed against the GitHub REST API, no cloning.

```bash
python3 commit_rate.py --org Unity-Environmental-University \
  --author unity-hallie \
  --range baseline:2024-05-06:2024-05-10 \
  --range current:2026-07-06:2026-07-10
```

```
METRIC TEMPLATE (repeat for up to 3)
Task or output: Commits to UEU repositories from my account
No-AI baseline: 5.2 commits/day
Expected outcome with Claude: 33.8 commits/day
Where this number comes from: git log --all --no-merges, author = unity-hallie, May 6–10 2024
vs Jul 6–10 2026. Repos = top 3 by total commit count among those active that week: baseline =
lxd-tools + lxd-tools-build; current = penelope + scher + ueu-dean-extension
```

## The rule

For each date range: check every repo in the org (via API) for commits
by `--author` (a GitHub login) in that window. Rank the repos that had
any activity by their **total historical commit count** — a proxy for
how substantial the codebase is, independent of the window being
measured, so there's no circularity. Keep the top N (default 3), sum
just those repos' commits in the window, divide by weekdays.

A single GitHub login is sufficient: the REST `author=` filter matches
by account, so it already includes every email linked to that account
(verified: `author=unity-hallie` and `author=hlarsson@unity.edu`
return identical commit sets on this org's repos).

`--detail` prints the full breakdown — which repos qualified, how many
commits each contributed.

Requires `gh auth login`.
