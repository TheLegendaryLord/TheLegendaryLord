# Max Verstappen profile tracker

The profile is updated by `.github/workflows/f1-tracker.yml` at minutes 17 and 47 of each hour (UTC). GitHub can delay scheduled jobs. The workflow also runs when its updater or tests change, and supports **Actions → F1 tracker → Run workflow**.

Data comes from the volunteer-maintained [Jolpica F1 API](https://github.com/jolpica/jolpica-f1), not a live timing feed. Only two API requests are needed per check: current driver standings and race results for the exact season/round reported by those standings. Championship points include points already recorded by the API, including sprints; the last-GP figure is for the race alone.

The card tracks Max's championship position, points, gap to the leader, GP wins, and last GP finish. The table shows the top five plus Max and nearby rivals when he is lower in the order. The full classification is expandable. Separate desktop/mobile SVGs share the same validated data. All drivers, points, names and season labels are read from the source; no current standings are hardcoded.

Run locally with Python 3.10+ (standard library only):

```sh
python3 -m unittest discover -s tests -v
python3 scripts/update_f1.py
```

The updater changes only the text between the `F1-TRACKER` markers, the two generated SVGs, and `data/f1.json`. It commits only when published data or the generated output changes. “Last change” records a change in the source snapshot, not each successful poll. Source failures, partial responses, mismatched rounds, missing Max, invalid points, and older-round rollbacks fail the job while retaining the published data. Inspect the linked Actions status if the snapshot stops advancing.

Before the first results of a new season are available, the previous valid snapshot remains visible with its actual season label. The year is never silently changed without standings. Future results automatically select the returned season. Number and team in the generated tracker come from the API; the decorative 2026 poster is a separate static fan artwork.

GitHub documents that [scheduled workflows in public repositories can be disabled after 60 days without repository activity](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), which can matter during the winter break. If disabled, re-enable the workflow in Actions and run it manually. No API keys, extra secrets, or external hosting are required. The workflow uses the repository's short-lived `GITHUB_TOKEN` with `contents: write` to publish results.

Sources: [Jolpica endpoints and user agent](https://github.com/jolpica/jolpica-f1/blob/main/docs/README.md), [API rate limits](https://github.com/jolpica/jolpica-f1/blob/main/docs/rate_limits.md), [Jolpica terms](https://github.com/jolpica/jolpica-f1/blob/main/TERMS.md). Jolpica data is provided under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) as specified by its terms; this fan tracker attributes the source and shares the cached data and generated standings under the same data license. The license does not apply to the separate poster or upstream photographs.
