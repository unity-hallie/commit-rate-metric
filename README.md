# commit-rate-metric

Commits/day, baseline period vs current period, computed against the
GitHub REST API — no cloning.

```bash
python3 commit_rate.py --org Unity-Environmental-University \
  --author unity-hallie \
  --range baseline:2024-01-01:2024-12-31 \
  --range current:2026-01-01:2026-09-04
```

```
METRIC TEMPLATE (repeat for up to 3)
Task or output: Commits to UEU repositories from my account
No-AI baseline: 1.7 commits/day (2024-01-01 to 2024-12-31)
Expected outcome with Claude: 6.7 commits/day (2026-01-01 to 2026-09-04)
Where this number comes from: https://github.com/unity-hallie/commit-rate-metric — author = unity-hallie.
Repos = top 3 by total commit count among those with a matching commit in range: baseline =
lxd-tools + LXD-Documentation + publish-script; current = penelope + lxd-tools + penelope-course
```

Runtime: ~10–15s for a full-year range against a ~120-repo org.

## Use a full period, not a single week

A single representative week is tempting — fast to eyeball, easy to
reproduce by hand — but it's unreliable: tested against four different
week pairs, the resulting ratio ranged from flat (0×) to ~10×, and one
pair even inverted (current lower than baseline), because week-level
commit activity is noisy and easily contaminated by unrelated
gaps — vacations, off days, or (in this case) a lapse in tool access
that happened to fall inside the sampled week. Use a range wide enough
that those gaps average out: a full year, or at minimum a full
quarter.

## The rule

For each date range: check every repo in the org (via API) for commits
by `--author` (a GitHub login) in that window. Rank the repos that had
any activity by their **total historical commit count** — a proxy for
how substantial the codebase is, independent of the window being
measured, so there's no circularity. Keep the top N (default 3), sum
just those repos' commits in the window, divide by workdays (Mon–Fri)
in the range.

A single GitHub login is sufficient: the REST `author=` filter matches
by account, so it already includes every email linked to that account
(verified: `author=unity-hallie` and `author=hlarsson@unity.edu`
return identical commit sets on this org's repos).

`--detail` prints the full breakdown — which repos qualified, how many
commits each contributed.

## Why not GitHub's pre-aggregated contributions API

`user.contributionsCollection.commitContributionsByRepository` would
replace the whole per-repo scan with one instant call — don't use it.
Verified against this org: it silently omits commits to **private**
repositories from the per-repo breakdown. In one test window it
omitted a private repo with more commits than every other repo in the
result combined, with no error and `restrictedContributionsCount`
reporting 0. This is a documented GitHub privacy behavior gated by the
account owner's own profile setting, not an org-admin permission, and
it makes the endpoint wrong by construction for any org where real
work lives in private repos. The slower per-repo REST scan
(`/repos/{owner}/{repo}/commits?author=...`) does not have this gap —
verified to return identical results to a full local
`git log --all --author=...` clone-based check.

Requires `gh auth login`.
