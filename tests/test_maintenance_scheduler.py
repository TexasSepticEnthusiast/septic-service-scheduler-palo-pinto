import re
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import outwestseptic_maintenance_scheduler as module
from outwestseptic_maintenance_scheduler import OutWestSepticMaintenanceScheduler

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "outwestseptic_maintenance_scheduler.py"


try:
    from icalendar import Calendar
except ImportError:
    Calendar = None


class ScheduleTests(unittest.TestCase):
    def schedule(self, **kwargs):
        return OutWestSepticMaintenanceScheduler.schedule(schedule_id="example-system", **kwargs)

    def test_last_service_uses_calendar_months(self):
        result = self.schedule(last_service=date(2024, 6, 1), interval_months=36, as_of=date(2026, 10, 18))
        self.assertEqual(result.next_due, date(2027, 6, 1))

    def test_january_31_does_not_drift_after_february(self):
        result = self.schedule(first_due=date(2025, 1, 31), interval_months=1, occurrences=3)
        self.assertEqual(result.dates, (date(2025, 1, 31), date(2025, 2, 28), date(2025, 3, 31)))

    def test_leap_anchor_restored(self):
        result = self.schedule(last_service=date(2024, 2, 29), interval_months=12,
                               occurrences=4, as_of=date(2024, 3, 1))
        self.assertEqual(result.dates[-1], date(2028, 2, 29))
        self.assertEqual(result.dates[0], date(2025, 2, 28))

    def test_one_time_due_without_interval(self):
        self.assertEqual(self.schedule(first_due=date(2030, 1, 1)).dates, (date(2030, 1, 1),))

    def test_overdue_dates_are_not_silently_skipped(self):
        result = self.schedule(first_due=date(2026, 1, 1), interval_months=1,
                               occurrences=3, as_of=date(2026, 2, 1))
        text = result.render()
        self.assertIn("2026-01-01: overdue", text)
        self.assertIn("2026-02-01: due today", text)
        self.assertIn("2026-03-01: upcoming", text)

    def test_invalid_or_ambiguous_dates(self):
        for args in [
            {}, dict(first_due=date.today(), last_service=date.today()),
            dict(first_due=datetime.now()), dict(first_due="2026-01-01"),
            dict(last_service=date(2030, 1, 1), interval_months=1, as_of=date(2026, 1, 1)),
            dict(last_service=date(2024, 1, 1)),
            dict(first_due=date(9999, 12, 31)),
            dict(first_due=date(9999, 12, 1), interval_months=1, occurrences=2),
            dict(first_due=date(2026, 1, 1), occurrences=2),
        ]:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    self.schedule(**args)

    def test_invalid_counts_and_text(self):
        for field, values in [
            ("interval_months", [0, -1, 1.5, True, 1201, float("nan")]),
            ("occurrences", [0, -1, True, 1.5, 121]),
            ("task", ["", "x\nInjected", "\x00"]),
            ("notes", ["\x00", "x" * 2001]),
        ]:
            for value in values:
                with self.subTest(field=field, value=repr(value)):
                    with self.assertRaises(ValueError):
                        self.schedule(first_due=date(2026, 1, 1), **{field: value})


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.stamp = datetime(2026, 10, 18, 12, 30, tzinfo=timezone(timedelta(hours=2)))
        self.schedule = OutWestSepticMaintenanceScheduler.schedule(
            schedule_id="calendar-example", first_due=date(2026, 1, 31),
            interval_months=1, occurrences=3, task="Inspection, check; test",
            notes="C:\\records\n" + "é漢" * 60 + "\r\nEND:VEVENT\nBEGIN:VEVENT",
        )

    def test_required_fields_real_one_day_events_and_utc_stamp(self):
        text = self.schedule.to_ics(generated_at=self.stamp)
        unfolded = text.replace("\r\n ", "")
        self.assertEqual(unfolded.split("\r\n").count("BEGIN:VEVENT"), 3)
        self.assertEqual(unfolded.count("UID:"), 3)
        self.assertEqual(unfolded.count("DTSTAMP:20261018T103000Z"), 3)
        self.assertIn("DTSTART;VALUE=DATE:20260131", unfolded)
        self.assertIn("DTEND;VALUE=DATE:20260201", unfolded)
        self.assertIn("DTSTART;VALUE=DATE:20260228", unfolded)
        self.assertIn("DTEND;VALUE=DATE:20260301", unfolded)
        self.assertNotIn("RRULE:", unfolded)

    def test_crlf_utf8_folding_and_text_escaping(self):
        text = self.schedule.to_ics(generated_at=self.stamp)
        self.assertNotIn("\n", text.replace("\r\n", ""))
        for line in text.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75)
            line.encode("utf-8").decode("utf-8")
        unfolded = text.replace("\r\n ", "")
        self.assertIn("SUMMARY:Inspection\\, check\\; test", unfolded)
        self.assertIn("C:\\\\records\\n", unfolded)
        self.assertIn("\\nEND:VEVENT\\nBEGIN:VEVENT", unfolded)

    def test_stable_unique_uids(self):
        first = re.findall(r"UID:(.+)\r\n", self.schedule.to_ics(generated_at=self.stamp))
        later = re.findall(r"UID:(.+)\r\n", self.schedule.to_ics(generated_at=self.stamp + timedelta(days=1)))
        self.assertEqual(first, later)
        self.assertEqual(len(set(first)), 3)

    @unittest.skipIf(Calendar is None, "Install requirements-test.txt for independent ICS parsing")
    def test_independent_parser_roundtrip(self):
        parsed = Calendar.from_ical(self.schedule.to_ics(generated_at=self.stamp))
        events = parsed.walk("VEVENT")
        self.assertEqual(len(events), 3)
        self.assertEqual([event.decoded("DTSTART") for event in events], list(self.schedule.dates))
        for event, due in zip(events, self.schedule.dates):
            self.assertEqual(event.decoded("DTEND"), due + timedelta(days=1))
            self.assertEqual(str(event["SUMMARY"]), self.schedule.task)
            normalized_notes = self.schedule.notes.replace("\r\n", "\n").replace("\r", "\n")
            self.assertTrue(str(event["DESCRIPTION"]).endswith(normalized_notes))
            self.assertEqual(event.decoded("DTSTAMP"), self.stamp.astimezone(timezone.utc))
            self.assertEqual(event.errors, [])

    def test_reject_naive_timestamp(self):
        with self.assertRaises(ValueError):
            self.schedule.to_ics(generated_at=datetime(2026, 1, 1))


class CliTests(unittest.TestCase):
    base = ["--schedule-id", "cli-example", "--last-service", "2024-06-01",
            "--interval-months", "36", "--as-of", "2026-10-18"]

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], input="",
                              capture_output=True, text=True, timeout=10)

    def test_real_calendar_file_export_without_optional_package(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "service.ics"
            result = self.run_cli(*self.base, "--ics", str(path), "--occurrences", "2")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("2027-06-01: upcoming", result.stdout)
            data = path.read_bytes()
            self.assertTrue(data.startswith(b"BEGIN:VCALENDAR\r\n"))
            self.assertEqual(data.count(b"BEGIN:VEVENT\r\n"), 2)
            self.assertIn(b"DTEND;VALUE=DATE:20270602\r\n", data)
            self.assertNotIn(b"\r\r\n", data)

    def test_existing_file_and_invalid_dates_cannot_clobber(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keep.ics"
            path.write_text("original")
            result = self.run_cli(*self.base, "--ics", str(path))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertEqual(path.read_text(), "original")
            result = self.run_cli("--schedule-id", "x", "--last-service", "invalid",
                                  "--interval-months", "36", "--ics", str(path), "--overwrite")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_text(), "original")
            result = self.run_cli(*self.base, "--ics", str(path), "--overwrite")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(path.read_bytes().startswith(b"BEGIN:VCALENDAR"))

    def test_failed_export_reports_no_success(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli(*self.base, "--ics", str(Path(directory) / "missing" / "service.ics"))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertNotIn("Traceback", result.stderr)

    def test_invalid_or_old_cli_is_clean_error(self):
        cases = [[], ["1250", "4"], self.base + ["--overwrite"],
                 ["--schedule-id", "x", "--first-due", "2025-02-29"],
                 ["--schedule-id", "x", "--first-due", "2026-1-1"],
                 ["--schedule-id", "x", "--first-due", "20260101"],
                 ["--schedule-id", "x", "--first-due", "2026-01-01", "--interval-months", "0"]]
        for args in cases:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("Traceback", result.stderr)

    def test_help(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)



class ExportSafetyTests(unittest.TestCase):
    formats = [("--ics", "to_ics")]
    base = ["--schedule-id", "example", "--first-due", "2030-01-01", "--task", "Example", "--notes", "Record"]

    def run_in_process(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(SystemExit) as failure:
            module.main(args)
        self.assertEqual(failure.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_api_rejects_surrogates_but_accepts_unicode(self):
        for value in ("bad" + chr(0xD800), "bad" + chr(0xDCFF)):
            for field in ("task", "notes"):
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "UTF-8"):
                    module.OutWestSepticMaintenanceScheduler.schedule(
                        schedule_id="example", first_due=date(2030, 1, 1), **{field: value})
        report = module.OutWestSepticMaintenanceScheduler.schedule(
            schedule_id="example", first_due=date(2030, 1, 1), task="Caf\u00e9 \U0001f69a")
        self.assertIn("Caf\u00e9 \U0001f69a", report.to_ics().encode("utf-8").decode("utf-8"))

    def test_bad_unicode_preserves_original_export_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "original.export"
            original = b"prior export\r\n\xff"
            for flag, _ in self.formats:
                for field, index in [("--task", 5), ("--notes", 7)]:
                    for surrogate in (0xD800, 0xDCFF):
                        with self.subTest(format=flag, field=field, surrogate=surrogate):
                            target.write_bytes(original)
                            args = self.base.copy()
                            args[index] = "Synthetic " + chr(surrogate)
                            self.run_in_process(args + [flag, str(target), "--overwrite"])
                            self.assertEqual(target.read_bytes(), original)
                            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_full_export_is_encoded_before_any_file_is_opened(self):
        # A future serializer change must not bypass the pre-write encoding check.
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "original.export"
            original = b"prior export"
            for flag, serializer in self.formats:
                for existing in (False, True):
                    with self.subTest(format=flag, existing=existing):
                        if existing:
                            target.write_bytes(original)
                        with patch.object(module.OutWestSepticMaintenanceSchedule, serializer, return_value=chr(0xD800)):
                            self.run_in_process(self.base + [flag, str(target), "--overwrite"])
                        if existing:
                            self.assertEqual(target.read_bytes(), original)
                        else:
                            self.assertFalse(target.exists())
                        self.assertEqual(list(Path(directory).iterdir()), [target] if existing else [])
                        target.unlink(missing_ok=True)

    def test_failed_atomic_overwrite_preserves_original_and_cleans_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "original.export"
            original = b"prior export\r\n\xff"
            real_temporary_file = module.tempfile.NamedTemporaryFile

            def fail_after_partial_write(*args, **kwargs):
                output = real_temporary_file(*args, **kwargs)
                real_write = output.write
                def partial_write(payload):
                    real_write(payload[:7])
                    raise OSError("simulated partial disk write")
                output.write = partial_write
                return output

            for flag, _ in self.formats:
                for phase in ("write", "fsync", "replace"):
                    with self.subTest(format=flag, failure=phase):
                        target.write_bytes(original)
                        if phase == "write":
                            failure = patch.object(module.tempfile, "NamedTemporaryFile", side_effect=fail_after_partial_write)
                        else:
                            failure = patch.object(module.os, phase, side_effect=OSError("simulated " + phase + " failure"))
                        with failure:
                            self.run_in_process(self.base + [flag, str(target), "--overwrite"])
                        self.assertEqual(target.read_bytes(), original)
                        self.assertEqual(list(Path(directory).iterdir()), [target])


if __name__ == "__main__":
    unittest.main()
