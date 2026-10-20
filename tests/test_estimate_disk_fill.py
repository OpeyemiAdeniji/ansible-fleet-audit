"""Unit tests for the disk-fill estimator. No servers and no Docker: the history is fake files."""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "estimate_disk_fill.py"
spec = importlib.util.spec_from_file_location("estimate_disk_fill", SCRIPT)
estimate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(estimate)

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
RUN_ID = NOW.strftime(estimate.RUN_ID_FORMAT)


def record(host, **mounts):
    """A minimal host record. Keyword names stand for mount points: root=42 means '/ 42%'."""
    names = {"root": "/", "var": "/var", "data": "/data"}
    return {"host": host, "disks": [f"{names[m]} {pct}%" for m, pct in mounts.items()]}


def write_history(folder, hours_ago, records):
    """Write one earlier audit file, named like the real ones."""
    when = NOW - timedelta(hours=hours_ago)
    path = Path(folder) / f"audit-{when.strftime(estimate.RUN_ID_FORMAT)}.json"
    path.write_text(json.dumps(records))
    return path


def run_estimate(folder, current, **options):
    samples = estimate.load_history(folder, NOW, options.get("window_hours", 24))
    samples.append((NOW, current))
    return estimate.estimate_hosts(
        estimate.build_series(samples),
        options.get("min_samples", 3),
        options.get("min_span_minutes", 30),
    )


class ParsingTests(unittest.TestCase):
    def test_run_id_becomes_a_utc_time(self):
        self.assertEqual(estimate.parse_run_id("20261020T120000Z"), NOW)

    def test_disk_lines_become_mount_and_percent(self):
        self.assertEqual(estimate.parse_disks(["/ 42%", "/var 87%"]), {"/": 42, "/var": 87})

    def test_mount_points_with_spaces_keep_their_name(self):
        self.assertEqual(estimate.parse_disks(["/mnt/my disk 60%"]), {"/mnt/my disk": 60})

    def test_broken_lines_are_ignored(self):
        self.assertEqual(estimate.parse_disks(["garbage", "/x abc%", "/y 50", "/ok 10%", None]), {"/ok": 10})

    def test_missing_disks_give_an_empty_result(self):
        self.assertEqual(estimate.parse_disks(None), {})


class EstimateTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = self._folder.name
        self.addCleanup(self._folder.cleanup)

    def test_steady_growth_gives_hours_to_full(self):
        # 80, 82, 84 and now 86: two points an hour, 14 points left, so 7 hours.
        for hours_ago, pct in [(3, 80), (2, 82), (1, 84)]:
            write_history(self.folder, hours_ago, [record("web-01", root=pct)])
        result = run_estimate(self.folder, [record("web-01", root=86)])["web-01"]
        self.assertEqual(result["status"], "estimated")
        self.assertEqual(result["hours_to_full"], 7.0)
        self.assertEqual(result["slope_pct_per_hour"], 2.0)
        self.assertEqual(result["mount"], "/")
        self.assertEqual(result["samples"], 4)

    def test_flat_disk_has_no_estimate(self):
        for hours_ago in (3, 2, 1):
            write_history(self.folder, hours_ago, [record("web-01", root=70)])
        result = run_estimate(self.folder, [record("web-01", root=70)])["web-01"]
        self.assertEqual(result, {"status": "not growing", "hours_to_full": None})

    def test_falling_disk_has_no_estimate(self):
        for hours_ago, pct in [(3, 90), (2, 80), (1, 70)]:
            write_history(self.folder, hours_ago, [record("web-01", root=pct)])
        result = run_estimate(self.folder, [record("web-01", root=60)])["web-01"]
        self.assertEqual(result["status"], "not growing")

    def test_two_samples_are_not_enough(self):
        write_history(self.folder, 1, [record("web-01", root=80)])
        result = run_estimate(self.folder, [record("web-01", root=90)])["web-01"]
        self.assertEqual(result, {"status": "not enough history", "hours_to_full": None})

    def test_samples_that_cover_too_little_time_are_not_enough(self):
        for minutes_ago, pct in [(10, 80), (5, 82)]:
            when = NOW - timedelta(minutes=minutes_ago)
            path = Path(self.folder) / f"audit-{when.strftime(estimate.RUN_ID_FORMAT)}.json"
            path.write_text(json.dumps([record("web-01", root=pct)]))
        result = run_estimate(self.folder, [record("web-01", root=84)])["web-01"]
        self.assertEqual(result["status"], "not enough history")

    def test_no_history_at_all_is_not_enough(self):
        result = run_estimate(self.folder, [record("web-01", root=90)])["web-01"]
        self.assertEqual(result["status"], "not enough history")

    def test_missing_history_folder_is_not_an_error(self):
        result = run_estimate(self.folder + "/does-not-exist", [record("web-01", root=90)])
        self.assertEqual(result["web-01"]["status"], "not enough history")

    def test_files_outside_the_window_are_ignored(self):
        # The 48 hour old file would make the line steeper if it were used.
        write_history(self.folder, 48, [record("web-01", root=10)])
        for hours_ago, pct in [(3, 80), (2, 82), (1, 84)]:
            write_history(self.folder, hours_ago, [record("web-01", root=pct)])
        result = run_estimate(self.folder, [record("web-01", root=86)])["web-01"]
        self.assertEqual(result["samples"], 4)
        self.assertEqual(result["hours_to_full"], 7.0)

    def test_a_file_for_the_current_run_is_not_counted_twice(self):
        for hours_ago, pct in [(3, 80), (2, 82), (1, 84)]:
            write_history(self.folder, hours_ago, [record("web-01", root=pct)])
        write_history(self.folder, 0, [record("web-01", root=99)])
        result = run_estimate(self.folder, [record("web-01", root=86)])["web-01"]
        self.assertEqual(result["samples"], 4)
        self.assertEqual(result["hours_to_full"], 7.0)

    def test_the_shortest_estimate_among_mounts_wins(self):
        for hours_ago, root, var in [(3, 40, 80), (2, 40, 85), (1, 41, 90)]:
            write_history(self.folder, hours_ago, [record("db-01", root=root, var=var)])
        result = run_estimate(self.folder, [record("db-01", root=41, var=95)])["db-01"]
        self.assertEqual(result["mount"], "/var")
        self.assertEqual(result["hours_to_full"], 1.0)

    def test_a_full_growing_disk_is_due_now(self):
        for hours_ago, pct in [(3, 97), (2, 98), (1, 99)]:
            write_history(self.folder, hours_ago, [record("web-01", root=pct)])
        result = run_estimate(self.folder, [record("web-01", root=100)])["web-01"]
        self.assertEqual(result["hours_to_full"], 0.0)

    def test_a_host_without_disk_data_is_reported_as_such(self):
        unreachable = {"host": "web-02", "status": "UNREACHABLE", "rank": 0}
        result = run_estimate(self.folder, [unreachable])["web-02"]
        self.assertEqual(result, {"status": "no disk data", "hours_to_full": None})

    def test_each_host_is_estimated_on_its_own(self):
        for hours_ago, a, b in [(3, 80, 50), (2, 82, 50), (1, 84, 50)]:
            write_history(self.folder, hours_ago, [record("web-01", root=a), record("web-02", root=b)])
        result = run_estimate(self.folder, [record("web-01", root=86), record("web-02", root=50)])
        self.assertEqual(result["web-01"]["status"], "estimated")
        self.assertEqual(result["web-02"]["status"], "not growing")


class BadHistoryTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = self._folder.name
        self.addCleanup(self._folder.cleanup)

    def test_unreadable_and_odd_files_are_skipped_with_a_warning(self):
        broken = write_history(self.folder, 2, [])
        broken.write_text("{not json")
        wrong_shape = write_history(self.folder, 1, [])
        wrong_shape.write_text('{"host": "web-01"}')
        warnings = io.StringIO()
        with redirect_stderr(warnings):
            samples = estimate.load_history(self.folder, NOW, 24)
        self.assertEqual(samples, [])
        self.assertIn(broken.name, warnings.getvalue())
        self.assertIn(wrong_shape.name, warnings.getvalue())

    def test_other_files_in_the_folder_are_ignored(self):
        (Path(self.folder) / "latest.json").write_text("[]")
        (Path(self.folder) / "audit-latest.json").write_text("[]")
        (Path(self.folder) / "audit-20261020T110000Z.csv").write_text("")
        self.assertEqual(estimate.load_history(self.folder, NOW, 24), [])

    def test_records_that_are_not_host_records_are_skipped(self):
        series = estimate.build_series([(NOW, ["text", 5, {"no": "host"}, record("web-01", root=50)])])
        self.assertEqual(list(series), ["web-01"])


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = self._folder.name
        self.addCleanup(self._folder.cleanup)

    def run_main(self, stdin_text, *extra):
        argv = ["--history-dir", self.folder, "--run-id", RUN_ID, *extra]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin_text)), redirect_stdout(out), redirect_stderr(err):
            code = estimate.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_end_to_end_prints_json(self):
        for hours_ago, pct in [(3, 80), (2, 82), (1, 84)]:
            write_history(self.folder, hours_ago, [record("web-01", root=pct)])
        code, out, _ = self.run_main(json.dumps([record("web-01", root=86)]))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["web-01"]["hours_to_full"], 7.0)

    def test_options_change_the_rules(self):
        for hours_ago, pct in [(3, 80), (2, 82), (1, 84)]:
            write_history(self.folder, hours_ago, [record("web-01", root=pct)])
        _, out, _ = self.run_main(json.dumps([record("web-01", root=86)]), "--min-samples", "10")
        self.assertEqual(json.loads(out)["web-01"]["status"], "not enough history")

    def test_invalid_json_on_stdin_is_an_error(self):
        code, _, err = self.run_main("not json")
        self.assertEqual(code, 2)
        self.assertIn("not valid JSON", err)

    def test_stdin_that_is_not_a_list_is_an_error(self):
        code, _, err = self.run_main('{"host": "web-01"}')
        self.assertEqual(code, 2)
        self.assertIn("list of host records", err)

    def test_a_bad_run_id_is_rejected(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            estimate.parse_args(["--history-dir", self.folder, "--run-id", "yesterday"])
        self.assertEqual(raised.exception.code, 2)


# A small fake fleet. Each host: (rank, status, service_down, current disk percent, disk percent 3, 2 and 1 hours ago).
FLEET = {
    "web-down": (1, "CRIT", True, 50, (50, 50, 50)),
    "web-fast": (1, "CRIT", False, 92, (83, 86, 89)),    # +3 points an hour: full in about 2.7 hours
    "web-slow": (1, "CRIT", False, 94, (92, 93, 93)),    # +0.6 points an hour: full in about 10 hours
    "web-flat": (1, "CRIT", False, 99, (99, 99, 99)),    # fullest disk, but not growing
    "app-fill": (2, "WARN", False, 85, (70, 75, 80)),    # +5 points an hour: full in 3 hours
    "app-stable": (2, "WARN", False, 88, (88, 88, 88)),  # fuller than app-fill, but not growing
    "app-ok": (3, "OK", False, 20, (20, 20, 20)),
}
UNREACHABLE = {"host": "db-unreachable", "role": "db", "status": "UNREACHABLE", "rank": 0, "issues": ["cannot connect over SSH"]}
BROKEN = {"host": "db-error", "role": "db", "status": "ERROR", "rank": 0, "issues": ["connected, but the audit tasks failed"]}


def fleet_records():
    records = [
        {"host": host, "status": status, "rank": rank, "service_down": down, "max_disk_pct": now, "disks": [f"/ {now}%"]}
        for host, (rank, status, down, now, _) in FLEET.items()
    ]
    return records + [dict(UNREACHABLE), dict(BROKEN)]


def write_fleet_history(folder):
    for index, hours_ago in enumerate((3, 2, 1)):
        records = [{"host": host, "disks": [f"/ {values[index]}%"]} for host, (*_, values) in FLEET.items()]
        write_history(folder, hours_ago, records)


class RankingTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = self._folder.name
        self.addCleanup(self._folder.cleanup)

    def ranked(self):
        records = fleet_records()
        return estimate.rank_records(records, run_estimate(self.folder, records))

    def test_hosts_are_ranked_by_urgency_when_there_is_history(self):
        write_fleet_history(self.folder)
        self.assertEqual(
            [r["host"] for r in self.ranked()],
            [
                "db-error", "db-unreachable",                        # no data at all: first, by name
                "web-down", "web-fast", "web-slow", "web-flat",      # CRIT: service down, then soonest full, then fullest
                "app-fill", "app-stable",                            # WARN: the filling disk beats the fuller, stable one
                "app-ok",
            ],
        )

    def test_without_history_the_fullest_disk_comes_first(self):
        self.assertEqual(
            [r["host"] for r in self.ranked()],
            [
                "db-error", "db-unreachable",
                "web-down", "web-flat", "web-slow", "web-fast",
                "app-stable", "app-fill",
                "app-ok",
            ],
        )

    def test_a_stopped_service_beats_a_disk_that_is_nearly_full(self):
        write_fleet_history(self.folder)
        ranked = [r["host"] for r in self.ranked() if r["status"] == "CRIT"]
        self.assertEqual(ranked[0], "web-down")

    def test_records_carry_the_estimate(self):
        write_fleet_history(self.folder)
        by_host = {r["host"]: r for r in self.ranked()}
        self.assertEqual(by_host["web-fast"]["disk_full_hours"], 2.7)
        self.assertEqual(by_host["web-fast"]["disk_full_mount"], "/")
        self.assertEqual(by_host["web-fast"]["disk_trend"], "estimated")
        self.assertEqual(by_host["web-slow"]["disk_full_hours"], 10.0)
        self.assertIsNone(by_host["web-flat"]["disk_full_hours"])
        self.assertEqual(by_host["web-flat"]["disk_trend"], "not growing")
        self.assertEqual(by_host["db-error"]["disk_trend"], "no disk data")

    def test_the_records_that_were_passed_in_are_not_changed(self):
        records = fleet_records()
        estimate.rank_records(records, {})
        self.assertNotIn("disk_trend", records[0])

    def test_the_same_data_always_gives_the_same_order(self):
        write_fleet_history(self.folder)
        first = [r["host"] for r in self.ranked()]
        self.assertEqual(first, [r["host"] for r in self.ranked()])

    def test_text_values_from_templating_still_sort_correctly(self):
        records = [
            {"host": "b", "rank": "1", "service_down": "False", "max_disk_pct": "50"},
            {"host": "a", "rank": "1", "service_down": "True", "max_disk_pct": "10"},
        ]
        self.assertEqual([r["host"] for r in estimate.rank_records(records, {})], ["a", "b"])

    def test_records_that_are_not_dicts_are_dropped(self):
        self.assertEqual(estimate.rank_records(["text", None, 5], {}), [])


class RankedCommandLineTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = self._folder.name
        self.addCleanup(self._folder.cleanup)

    def run_main(self, *extra, stdin_text=""):
        argv = ["--history-dir", self.folder, "--run-id", RUN_ID, *extra]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin_text)), redirect_stdout(out), redirect_stderr(err):
            code = estimate.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_ranked_output_is_a_list_in_report_order(self):
        write_fleet_history(self.folder)
        current = Path(self.folder) / "current.json"  # the name does not match audit-*.json, so it is not history
        current.write_text(json.dumps(fleet_records()))
        code, out, _ = self.run_main("--ranked", "--current", str(current))
        self.assertEqual(code, 0)
        hosts = [r["host"] for r in json.loads(out)]
        self.assertEqual(hosts[:4], ["db-error", "db-unreachable", "web-down", "web-fast"])
        self.assertEqual(len(hosts), len(FLEET) + 2)

    def test_a_missing_current_file_is_an_error(self):
        code, _, err = self.run_main("--current", "/does/not/exist.json")
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_ranking_works_when_history_is_empty(self):
        code, out, _ = self.run_main("--ranked", stdin_text=json.dumps(fleet_records()))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)[0]["host"], "db-error")


if __name__ == "__main__":
    unittest.main()
