# Palo Pinto septic service reminder calendar

Create dated maintenance reminders from a service plan you choose. Supply a first due date, or a known last-service date and a calendar-month interval. Export real all-day iCalendar events without optional runtime dependencies.

An AI-assisted automated contribution for the [Out West Septic](https://outwestseptic.com) project. This is affiliated planning software. It does not infer pumping frequency or record work as completed.

## Create reminders

Python 3.10 or newer.

```bash
git clone https://github.com/TexasSepticEnthusiast/septic-service-scheduler-palo-pinto.git
cd septic-service-scheduler-palo-pinto
python scripts/outwestseptic_maintenance_scheduler.py --schedule-id example-system --last-service 2024-06-01 --interval-months 36 --occurrences 2 --as-of 2026-10-18 --ics service-reminders.ics
```

This **illustrative schedule choice** creates reminders for **2027-06-01** and **2030-06-01**. It is not a recommended maintenance interval.

If the last service date is unknown, choose an explicit first reminder instead:

```bash
python scripts/outwestseptic_maintenance_scheduler.py --schedule-id example-inspection --first-due 2026-11-01 --task "Confirm service plan" --ics first-reminder.ics
```

The program never substitutes today's date for an unknown or invalid service date.

## Choose dates deliberately

- Supply exactly one of `--first-due YYYY-MM-DD` or `--last-service YYYY-MM-DD`.
- `--interval-months` has no default. It is required with last-service dates or multiple occurrences. Whole values from 1 through 1200 are supported.
- `--occurrences` chooses 1 through 120 reminders and defaults to one.
- `--schedule-id` is a stable identifier unique to the system **and task**; use a different ID for an inspection and a pumping reminder.
- `--task` labels the reminder; `--notes` adds optional notes. Both require valid Unicode text encodable as UTF-8.
- `--as-of` controls overdue/due/upcoming status and defaults to the computer's local date. Last-service dates after that date are rejected.
- Past reminders remain visible as overdue. The program does not assume a missed service was completed.

Calendar months use the original anchor day. January 31 at monthly intervals becomes February 28 (or 29), then March 31. A February 29 annual anchor returns to February 29 in the next leap year. These are explicit software scheduling conventions, not maintenance rules.

## Calendar export behavior

`--ics PATH` writes a UTF-8 file with CRLF endings, one all-day event per listed date, stable event identifiers, a UTC generation timestamp, an exclusive next-day end date, and escaped/folded text. Dated events avoid time-zone and daylight-saving shifts.

The export contains a finite set of events rather than a repeating rule. That preserves month-end dates and supports intervals such as 18 months without rounding them to years. Re-exporting the same schedule ID and date retains its event UID. Import behavior depends on the calendar application; this tool does not synchronize or remove old reminders. If dates change, review and remove obsolete imported events.

Existing files require explicit `--overwrite`. The complete calendar is encoded before any file is opened. Overwrites are written and flushed to a temporary file in the destination directory, then atomically replace the old file; encoding, staging-write or replacement failures preserve the old bytes. Invalid inputs and failed writes exit with status 2 without claiming an export succeeded. The parent directory must exist. No email, booking, alarm notification, or external calendar write is performed.

## Python API

```python
from datetime import date
from scripts.outwestseptic_maintenance_scheduler import OutWestSepticMaintenanceScheduler

schedule = OutWestSepticMaintenanceScheduler.schedule(
    schedule_id="example-system",
    last_service=date(2024, 6, 1),
    interval_months=36,
    occurrences=2,
    as_of=date(2026, 10, 18),
)
print(schedule.next_due)  # 2027-06-01
calendar_text = schedule.to_ics()
```

## Guidance and migration

Choose the schedule using actual service records, your provider's advice, the system's requirements, and the permitting authority's rules. See the [primary-source and calendar reference](wiki/Maintenance-Scheduler-Reference.md).

The old tank/household lookup and garbage-disposal/water-softener multipliers lacked verifiable support and were removed. The positional tank/household arguments, `--last-pumped`, `--disposal`, and `--softener` are replaced by explicit dates and intervals. Old calls fail rather than silently selecting a different schedule.

`OutWestSepticMaintenanceScheduler` remains the main class; `MaintenanceSchedule` is an import alias for `OutWestSepticMaintenanceSchedule`. Its fields and constructor have changed. Fictitious seed histories were removed. The script and guides no longer make unverified business-service claims.

## Validate and license

Runtime uses only the standard library. Install the pinned **test-only** parser to check the generated calendar independently:

```bash
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
```

Without the parser, the standard-library tests still run and the independent parser test is explicitly skipped. CI installs the parser and tests Python 3.10 and 3.13. Calendar tests cover leap years, month ends, overdue dates, escaping, UTF-8 folding, UTC timestamps, exclusive end dates, exports, invalid Unicode, and original-file preservation during simulated partial-write, flush and replacement failures. Import into specific calendar applications has not been tested.

See the existing [license reference](LICENSE).
