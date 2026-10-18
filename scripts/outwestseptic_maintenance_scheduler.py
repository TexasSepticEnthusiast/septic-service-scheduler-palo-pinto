"""Calendar reminders from explicit service dates and chosen month intervals.

AI-assisted contribution for Jake's Out West Septic project.
See the repository documentation for source and scope limitations.
"""
from __future__ import annotations

import argparse
import calendar
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5


def _date(value: date, label: str) -> date:
    if type(value) is not date:
        raise ValueError(f"{label} must be a date without a time.")
    return value


def _parse_date(raw: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw):
        raise argparse.ArgumentTypeError("Use a valid date in YYYY-MM-DD format.")
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise argparse.ArgumentTypeError("Use a valid date in YYYY-MM-DD format.") from None


def _integer(value: int, label: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{label} must be a whole number from 1 to {maximum}.")
    return value


def _text(value: str, label: str, maximum: int, multiline: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f"{label} must be text of at most {maximum} characters.")
    allowed = "\r\n\t" if multiline else ""
    if any((ord(char) < 32 and char not in allowed) or ord(char) == 127 for char in value):
        raise ValueError(f"{label} contains an unsupported control character.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(f"{label} must contain valid Unicode text encodable as UTF-8.") from None
    return value


def _add_months(anchor: date, months: int) -> date:
    """Clamp to the target month's last day, always using the original anchor."""
    year, month_index = divmod(anchor.year * 12 + anchor.month - 1 + months, 12)
    if not 1 <= year <= 9999:
        raise ValueError("The selected schedule exceeds the supported calendar date range.")
    month = month_index + 1
    return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))


def _escape_ics(text: str) -> str:
    return (text.replace("\r\n", "\n").replace("\r", "\n")
            .replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def _fold_ics(line: str) -> str:
    """Fold to at most 75 UTF-8 octets per RFC 5545, including continuation space."""
    parts = []
    current = ""
    octets = 0
    for character in line:
        width = len(character.encode("utf-8"))
        if octets + width > 75:
            parts.append(current)
            current = " "
            octets = 1
        current += character
        octets += width
    parts.append(current)
    return "\r\n".join(parts)


class OutWestSepticMaintenanceScheduler:
    """Build reminders; the caller chooses the applicable maintenance schedule."""

    @staticmethod
    def schedule(
        *, schedule_id: str, first_due: date | None = None,
        last_service: date | None = None, interval_months: int | None = None,
        occurrences: int = 1, task: str = "Septic service reminder",
        notes: str = "", as_of: date | None = None,
    ) -> "OutWestSepticMaintenanceSchedule":
        if not isinstance(schedule_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", schedule_id):
            raise ValueError("Schedule ID must be 1 to 100 letters, digits, periods, underscores or hyphens.")
        task = _text(task, "Task", 200).strip()
        if not task:
            raise ValueError("Task must not be empty.")
        notes = _text(notes, "Notes", 2000, multiline=True)
        count = _integer(occurrences, "Occurrences", 120)
        if (first_due is None) == (last_service is None):
            raise ValueError("Supply exactly one of first_due or last_service.")
        if interval_months is not None:
            _integer(interval_months, "Interval months", 1200)
        if interval_months is None and (last_service is not None or count > 1):
            raise ValueError("Interval months is required with last_service or multiple occurrences.")
        anchor = _date(first_due if first_due is not None else last_service, "Anchor date")
        reference = date.today() if as_of is None else _date(as_of, "As-of date")
        if last_service is not None and last_service > reference:
            raise ValueError("Last-service date cannot be after the as-of date; use first_due for a future plan.")
        start = 0 if first_due is not None else 1
        dates = tuple(_add_months(anchor, (interval_months or 0) * index)
                      for index in range(start, start + count))
        if dates[-1] == date.max:
            raise ValueError("A reminder must allow the following date for its exclusive calendar end.")
        return OutWestSepticMaintenanceSchedule(
            schedule_id, task, notes, anchor,
            "first_due" if first_due is not None else "last_service",
            interval_months, dates, reference,
        )


@dataclass(frozen=True)
class OutWestSepticMaintenanceSchedule:
    schedule_id: str
    task: str
    notes: str
    anchor_date: date
    anchor_kind: str
    interval_months: int | None
    dates: tuple[date, ...]
    as_of: date

    @property
    def next_due(self) -> date:
        return self.dates[0]

    def render(self) -> str:
        lines = [
            "Out West Septic project - Maintenance reminders",
            f"Schedule: {self.schedule_id}",
            f"Task: {self.task}",
            f"Supplied {self.anchor_kind.replace('_', ' ')}: {self.anchor_date.isoformat()}",
            f"Chosen interval: {self.interval_months} calendar months" if self.interval_months else "One dated reminder",
            f"Status as of: {self.as_of.isoformat()}",
        ]
        for due in self.dates:
            status = "overdue" if due < self.as_of else "due today" if due == self.as_of else "upcoming"
            lines.append(f"- {due.isoformat()}: {status}")
        if self.notes:
            lines.append(f"Notes: {self.notes}")
        lines.append("Dates reflect your choices; confirm requirements with your provider and permitting authority.")
        return "\n".join(lines)

    def to_ics(self, *, generated_at: datetime | None = None) -> str:
        stamp = datetime.now(timezone.utc) if generated_at is None else generated_at
        if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("Calendar generation time must be a timezone-aware datetime.")
        stamp = stamp.astimezone(timezone.utc)
        dtstamp = (f"{stamp.year:04d}{stamp.month:02d}{stamp.day:02d}T"
                   f"{stamp.hour:02d}{stamp.minute:02d}{stamp.second:02d}Z")
        lines = [
            "BEGIN:VCALENDAR", "VERSION:2.0",
            "PRODID:-//Out West Septic project//Maintenance Scheduler//EN",
            "CALSCALE:GREGORIAN",
        ]
        description = (
            f"User-chosen reminder. Schedule ID: {self.schedule_id}. "
            f"Anchor: {self.anchor_date.isoformat()} ({self.anchor_kind}). "
            f"Interval months: {self.interval_months if self.interval_months else 'one-time'}. "
            "Confirm the service plan with your provider and permitting authority."
        )
        if self.notes:
            description += "\n" + self.notes
        for due in self.dates:
            uid = uuid5(NAMESPACE_URL, f"outwestseptic-maintenance:{self.schedule_id}:{due.isoformat()}")
            lines.extend([
                "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{dtstamp}",
                f"DTSTART;VALUE=DATE:{due.isoformat().replace('-', '')}",
                f"DTEND;VALUE=DATE:{(due + timedelta(days=1)).isoformat().replace('-', '')}",
                f"SUMMARY:{_escape_ics(self.task)}",
                f"DESCRIPTION:{_escape_ics(description)}",
                "TRANSP:TRANSPARENT", "END:VEVENT",
            ])
        lines.append("END:VCALENDAR")
        return "\r\n".join(_fold_ics(line) for line in lines) + "\r\n"


MaintenanceSchedule = OutWestSepticMaintenanceSchedule


def _write_export(target: Path, content: str, *, overwrite: bool) -> None:
    """Encode before opening files; stage replacements beside the destination."""
    payload = content.encode("utf-8")
    if not overwrite:
        with target.open("xb") as output:
            output.write(payload)
        return
    staged = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent, prefix=".outwestseptic-export-",
            suffix=".tmp", delete=False,
        ) as output:
            staged = Path(output.name)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(staged, target)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create dated service reminders from a schedule you choose.",
        allow_abbrev=False,
    )
    parser.add_argument("--schedule-id", required=True, help="Stable identifier unique to this system and task.")
    dates = parser.add_mutually_exclusive_group(required=True)
    dates.add_argument("--first-due", type=_parse_date, metavar="YYYY-MM-DD")
    dates.add_argument("--last-service", type=_parse_date, metavar="YYYY-MM-DD")
    parser.add_argument("--interval-months", type=int, help="Chosen calendar-month interval; no default.")
    parser.add_argument("--occurrences", type=int, default=1, help="Number of reminders, 1 to 120; default 1.")
    parser.add_argument("--task", default="Septic service reminder")
    parser.add_argument("--notes", default="")
    parser.add_argument("--as-of", type=_parse_date, help="Status reference date; default local today.")
    parser.add_argument("--ics", type=Path, metavar="PATH", help="Export all-day iCalendar reminders.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing the selected calendar file.")
    args = parser.parse_args(argv)
    try:
        schedule = OutWestSepticMaintenanceScheduler.schedule(
            schedule_id=args.schedule_id, first_due=args.first_due, last_service=args.last_service,
            interval_months=args.interval_months, occurrences=args.occurrences,
            task=args.task, notes=args.notes, as_of=args.as_of,
        )
        if args.overwrite and args.ics is None:
            raise ValueError("--overwrite requires --ics.")
        if args.ics is not None:
            content = schedule.to_ics()
            _write_export(args.ics, content, overwrite=args.overwrite)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(schedule.render())
    if args.ics is not None:
        print(f"Calendar written: {args.ics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
