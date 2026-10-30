import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

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


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = "keep this header\n" + f1.START + "\nold tracker\n" + f1.END + "\nkeep this artwork credit\n"
        (self.root / "README.md").write_text(self.original, encoding="utf-8")
        self.standings, self.race = documents()

    def fetch(self, url):
        if "driverstandings" in url:
            return copy.deepcopy(self.standings)
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
        self.assertIn("30 очков до лидера", readme)
        self.assertIn("**Max Verstappen**", readme)
        self.assertIn("+15 очков в гонке", readme)
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
        self.assertIn("40.5 очков", readme)
        self.assertIn("29.5 очков до лидера", readme)

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


if __name__ == "__main__":
    unittest.main()
