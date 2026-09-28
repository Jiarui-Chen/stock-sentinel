"""
Per-run record of which analysis stages failed, so the report can say so.

Every Claude-backed stage degrades to an empty result rather than aborting the
run — a scorecard-only report beats no report at all. The cost is that failure
renders *identically* to a genuinely quiet day: no news, no picks, no option-flow
highlights, no commentary. That is how an 11-day Anthropic credit outage
(2026-09-16 onward) went unnoticed — eleven normal-looking emails, every
AI-written section silently dropped.

Stages call record() in their except blocks; the reporter drains failures() and
renders a banner naming what is missing and why. Module-level state is
deliberate: it keeps the failure path out of four analyzer signatures and out of
the call chain between them. Single-threaded by design — the scheduler runs one
job at a time — and reset() must be called at the start of each run, or one day's
failures leak into the next day's email in the long-lived launchd process.
"""

from __future__ import annotations

# Section keys map to i18n section headers, so the banner names a section with
# exactly the label the reader sees on it elsewhere in the email.
SECTION_KEYS = {
    "commentary": "sec_commentary",
    "news":       "sec_news",
    "picks":      "sec_picks",
    "flow":       "sec_flow",
}

_REASON_MARKERS = (
    ("credit balance is too low", "reason_credit"),
    ("invalid x-api-key",         "reason_auth"),
    ("authentication_error",      "reason_auth"),
    ("rate_limit",                "reason_rate_limit"),
    ("connection error",          "reason_network"),
    ("timed out",                 "reason_network"),
    ("timeout",                   "reason_network"),
)

# (section_key, reason_key) pairs, deduplicated, in first-seen order. Dedup
# matters: news is analyzed in batches, so one outage produces a failure per
# batch — 169 of them during the September outage — all naming the same cause.
_failures: list[tuple[str, str]] = []


def _classify(exc: Exception) -> str:
    """Map an exception to a reason key the reader can act on."""
    text = str(exc).lower()
    for marker, reason in _REASON_MARKERS:
        if marker in text:
            return reason
    return "reason_unknown"


def record(section: str, exc: Exception) -> None:
    """Note that `section` could not be generated because of `exc`."""
    if section not in SECTION_KEYS:
        raise ValueError(f"unknown section {section!r}")
    entry = (section, _classify(exc))
    if entry not in _failures:
        _failures.append(entry)


def failures() -> list[tuple[str, str]]:
    """The failures recorded so far this run, as (section key, reason key)."""
    return list(_failures)


def reset() -> None:
    """Clear the record. Call at the start of every run."""
    _failures.clear()
