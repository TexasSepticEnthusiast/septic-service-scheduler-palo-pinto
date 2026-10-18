# Maintenance schedule choices and calendar format

Prepared as an AI-assisted automated contribution for Jake's [Out West Septic](https://outwestseptic.com) project.

## What the authorities establish

[TCEQ maintenance guidance](https://www.tceq.texas.gov/permitting/ossf/ossfmaintenance.html) describes maintenance obligations and notes that local permitting authorities may impose more stringent requirements. Maintenance contracts and the actual system matter. The [TCEQ owner's guide](https://www.tceq.texas.gov/permitting/ossf/ossfadvice.html) provides further operation and maintenance information.

[EPA's household septic-care guidance](https://www.epa.gov/septic/how-care-your-septic-system) identifies household size, wastewater generation, solids, and tank size as factors affecting pumping frequency. It also emphasizes inspection findings and service records. Those observations do not justify the old repository's nearest-row interval lookup or numerical softener/disposal multipliers.

This tool therefore **records your chosen dates and interval**. It does not determine the required pumping interval for a specific system. If the correct interval or last-service date is unknown, resolve that with the service provider and permitting authority; a separate first-due reminder can be used to follow up.

## Date contract

The user supplies either a first due date or a known last-service date. A last-service date requires an explicit month interval and cannot be in the future relative to the chosen as-of date.

For a last-service anchor, the first reminder is one interval after the anchor. For a first-due anchor, the first reminder is that date. Later reminders use the original anchor plus whole multiples of the interval. If the anchor day does not exist in a target month, it is clamped to that month's last day. Later months still use the original day.

Example only: January 31, 2025 plus one and two months yields February 28 and March 31. There is no 365-day approximation, rolling drift, or rounding a fractional-year interval to whole years. Dates outside the supported calendar range are rejected.

## iCalendar contract

[RFC 5545](https://www.rfc-editor.org/rfc/rfc5545.txt) supplies the format rules:

- §3.1: CRLF content lines and line folding; output lines stay within 75 UTF-8 octets without splitting characters.
- §3.3.11: text escaping for backslashes, commas, semicolons, and newlines.
- §3.6.1: event structure, UID, DTSTAMP, DTSTART, and a non-inclusive DTEND.
- §§3.8.7.2 and 3.8.4.7: creation timestamp and unique identifier.

Each reminder becomes one all-day VEVENT, with its end date on the following day. Explicit dates preserve month-end choices without recurrence-rule ambiguity. UID derives from the supplied schedule ID and event date; the generation timestamp is UTC. No alarm or external booking is created.

The test suite parses exports using the separate `icalendar` package and checks the resulting dates and text. Calendar-client import behavior is still an application-specific check.

## Sources and review status

The TCEQ, EPA, and RFC sources above were reviewed on 2026-10-18. General educational guidance is not a site-specific service plan, and this repository does not maintain a jurisdiction-by-jurisdiction maintenance-rule database.

No owner decision blocks use of the explicit-date workflow. Automatically recommending intervals in a future version would require a supported method, defined system scope, and owner approval of its maintenance responsibilities.
