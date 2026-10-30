import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("update_f1", Path(__file__).resolve().parents[1] / "scripts/update_f1.py")
f1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(f1)
NOW = datetime(2026, 10, 30, 18, 0, tzinfo=timezone.utc)


def documents(count=7, max_index=3):
    rows = []
    results = []
    for i in range(count):
        driver = {"driverId": f1.DRIVER if i == max_index else f"driver_{i}",
                  "givenName": "Max" if i == max_index else "Test",
                  "familyName": "Verstappen" if i == max_index else f"Driver {i}",
                  "permanentNumber": "3" if i == max_index else str(i+10)}
        rows.append({"position": str(i+1), "points": str((count-i)*10), "wins": "2",
                     "Driver": driver, "Constructors": [{"name": "Red Bull Racing"}]})
        results.append({"position": str(i+1), "points": "15", "status": "Finished", "Driver": driver})
    standings = {"MRData": {"series": "f1", "offset": "0", "total": str(count),
        "StandingsTable": {"StandingsLists": [{"season": "2026", "round": "18", "DriverStandings": rows}]}}}
    race = {"MRData": {"series": "f1", "offset": "0", "total": str(count),
        "RaceTable": {"Races": [{"season": "2026", "round": "18", "raceName": "Test Grand Prix",
                                "date": "2026-10-25", "Results": results}]}}}
    return standings, race


def season_document(race):
    last_race = race["MRData"]["RaceTable"]["Races"][0]
    last_result = next(row for row in last_race["Results"] if row["Driver"]["driverId"] == f1.DRIVER)
    positions = [1, 2, 3, 4, 1, 2, 3, 4, 2, 3, 5, 6, 8, 9, 10, 11, 12]
    scoring = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}
    races = []
    for round_number, position in enumerate(positions, 1):
        result = copy.deepcopy(last_result)
        result.update(position=str(position), points=str(scoring.get(position, 0)))
        races.append({"season": "2026", "round": str(round_number), "raceName": f"Test GP {round_number}",
                      "date": f"2026-09-{round_number:02}",
                      "Circuit": {"Location": {"locality": f"Venue {round_number}"}}, "Results": [result]})
    final = copy.deepcopy(last_race)
    final["Results"] = [copy.deepcopy(last_result)]
    races.append(final)
    return {"MRData": {"series": "f1", "offset": "0", "total": "18", "RaceTable": {"Races": races}}}


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = "keep this header\n" + f1.START + "\nold tracker\n" + f1.END + "\nkeep this artwork credit\n"
        (self.root / "README.md").write_text(self.original, encoding="utf-8")
        self.standings, self.race = documents()
        self.season = season_document(self.race)

    def fetch(self, url):
        if "driverstandings" in url:
            return copy.deepcopy(self.standings)
        if "/drivers/max_verstappen/results.json" in url:
            return copy.deepcopy(self.season)
        self.assertIn("/2026/18/results.json", url)
        return copy.deepcopy(self.race)

    def update(self):
        return f1.update(self.root, fetch=self.fetch, now=NOW)

    def test_publishes_correct_max_metrics_and_preserves_profile(self):
        changed = self.update()
        self.assertEqual(len(changed), 4)
        state = json.loads((self.root / "data/f1.json").read_text(encoding="utf-8"))
        self.assertEqual(f1.max_driver(state)["points"], "40")
        self.assertEqual(f1.max_driver(state)["position"], 4)
        readme = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertTrue(readme.startswith("keep this header\n"))
        self.assertTrue(readme.endswith("\nkeep this artwork credit\n"))
        self.assertIn("30 points behind the leader", readme)
        self.assertIn("**Max Verstappen**", readme)
        self.assertIn("+15 race points", readme)
        for filename in ("f1-max.svg", "f1-max-mobile.svg"):
            ElementTree.parse(self.root / "assets" / filename)

    def test_unchanged_results_do_not_change_files_or_timestamp(self):
        self.update()
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        changed = f1.update(self.root, fetch=self.fetch, now=datetime(2026, 10, 31, tzinfo=timezone.utc))
        self.assertEqual(changed, [])
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_fractional_points_are_exact(self):
        rows = self.standings["MRData"]["StandingsTable"]["StandingsLists"][0]["DriverStandings"]
        rows[3]["points"] = "40.5"
        self.update()
        readme = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertIn("40.5 points", readme)
        self.assertIn("29.5 points behind the leader", readme)

    def test_missing_or_partial_source_preserves_last_good_snapshot(self):
        self.update()
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.standings["MRData"]["total"] = "22"
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            self.update()
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_network_failure_does_not_overwrite_readme(self):
        def unavailable(url):
            raise OSError("API unavailable")
        with self.assertRaises(OSError):
            f1.update(self.root, fetch=unavailable, now=NOW)
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"), self.original)
        self.assertFalse((self.root / "data/f1.json").exists())

    def test_mismatched_round_is_rejected_before_writing(self):
        self.race["MRData"]["RaceTable"]["Races"][0]["round"] = "19"
        with self.assertRaisesRegex(ValueError, "different rounds"):
            self.update()
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"), self.original)

    def test_duplicate_drivers_and_missing_max_are_rejected(self):
        rows = self.standings["MRData"]["StandingsTable"]["StandingsLists"][0]["DriverStandings"]
        rows[3]["Driver"]["driverId"] = "driver_0"
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.update()
        rows[3]["Driver"]["driverId"] = "someone_else"
        with self.assertRaisesRegex(ValueError, "absent"):
            self.update()

    def test_nan_infinite_and_negative_points_are_rejected(self):
        for value in ("NaN", "Infinity", "-1", "not a number"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                f1.points(value)

    def test_classified_retirement_is_not_presented_as_a_finish(self):
        self.assertEqual(f1.finish_label({"position": "18", "status": "Engine"}), "DNF (P18)")
        self.assertEqual(f1.finish_label({"position": "10", "status": "+1 Lap"}), "P10")
        self.assertEqual(f1.finish_label({"position": "18", "status": "Disqualified"}), "DSQ")

    def test_compact_table_includes_max_outside_top_five(self):
        standings, _ = documents(12, 10)
        state = f1.parse_standings(standings)
        table = f1.standings_table(state, compact=True)
        self.assertIn("**11** | **Max Verstappen**", table)
        self.assertIn("| 10 |", table)
        self.assertIn("| 12 |", table)
        self.assertIn("| … |", table)

    def test_older_round_cannot_replace_published_data(self):
        self.update()
        old = json.loads((self.root / "data/f1.json").read_text(encoding="utf-8"))
        old["round"] = 19
        (self.root / "data/f1.json").write_text(json.dumps(old), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "older round"):
            self.update()

    def test_bad_markers_cannot_replace_other_profile_content(self):
        for readme in ("no markers", f1.END + f1.START, f1.START + f1.START + f1.END):
            with self.subTest(readme=readme), self.assertRaises(ValueError):
                f1.replace_block(readme, "new content")

    def test_image_cache_key_changes_when_artwork_changes(self):
        self.update()
        state = json.loads((self.root / "data/f1.json").read_text(encoding="utf-8"))
        before = f1.render_block(state)
        with patch.object(f1, "render_svg", return_value="new card design"):
            after = f1.render_block(state)
        self.assertNotEqual(before, after)

    def test_season_summary_and_form_use_gp_results(self):
        self.update()
        state = json.loads((self.root / "data/f1.json").read_text(encoding="utf-8"))
        self.assertEqual(state["season_stats"], {"starts": 18, "podiums": 8, "gp_points": "213"})
        self.assertEqual([r["round"] for r in state["recent_results"]], [14, 15, 16, 17, 18])
        self.assertEqual([r["finish"] for r in state["recent_results"]], ["P9", "P10", "P11", "P12", "P4"])

    def test_partial_season_history_preserves_published_files(self):
        self.update()
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.season["MRData"]["total"] = "19"
        with self.assertRaisesRegex(ValueError, "Incomplete season"):
            self.update()
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_history_cannot_disagree_with_last_race(self):
        self.season["MRData"]["RaceTable"]["Races"][-1]["Results"][0]["points"] = "18"
        with self.assertRaisesRegex(ValueError, "last GP disagree"):
            self.update()
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"), self.original)

    def test_history_does_not_include_races_ahead_of_standings(self):
        self.update()
        future = copy.deepcopy(self.season["MRData"]["RaceTable"]["Races"][-1])
        future["round"] = "19"
        future["Results"][0].update(position="1", points="25")
        self.season["MRData"]["RaceTable"]["Races"].append(future)
        self.season["MRData"]["total"] = "19"
        self.assertEqual(self.update(), [])

    def test_context_handles_championship_leader_and_last_place(self):
        state = f1.parse_standings(documents(7, 0)[0])
        self.assertEqual([row["position"] for row in f1.championship_rows(state)], [1, 2])
        state = f1.parse_standings(documents(7, 6)[0])
        self.assertEqual([row["position"] for row in f1.championship_rows(state)], [1, 6, 7])


if __name__ == "__main__":
    unittest.main()


