"""
Regression guard for silently-degraded reports.

Every Claude-backed stage catches its own exceptions and returns an empty result
so the run still produces a report. The failure mode this guards against is that
an empty section is indistinguishable from a quiet day: when the Anthropic credit
balance hit zero on 2026-09-16, eleven consecutive emails arrived looking normal
— correct subject line, correct signal count — with news, picks, commentary and
option flow all silently missing. It took a week to notice.

src/degradation.py records what failed and the reporter renders a banner naming
it. These checks pin the four invariants that make the banner trustworthy:

  * a failure in any stage reaches the rendered email,
  * a clean run renders no banner at all (no false alarms),
  * repeated failures of one batched stage collapse to a single line,
  * state does not leak between runs in the long-lived launchd process.

All hermetic — no network, no API calls. Runs under pytest, or standalone:
`python3 tests/test_degraded_report.py`.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import degradation, i18n
from src.report import email_reporter

# The verbatim error that produced the September outage.
CREDIT_ERROR = Exception(
    "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
    "'message': 'Your credit balance is too low to access the Anthropic API. "
    "Please go to Plans & Billing to upgrade or purchase credits.'}}"
)

_BANNER_RE = re.compile(r'background:#fffbeb.*?</div>\s*</div>', re.S)


def _banner_text(degradations) -> str:
    """The banner's visible text, tags stripped, or "" when no banner rendered."""
    html = email_reporter.build_html([], None, None, None, degradations)
    m = _BANNER_RE.search(html)
    return re.sub(r"<[^>]+>", " ", m.group(0)) if m else ""


def test_failure_is_visible_in_email():
    """A failed stage must be named in the rendered email, not silently dropped."""
    degradation.reset()
    degradation.record("picks", CREDIT_ERROR)
    text = _banner_text(degradation.failures())
    assert text, "stage failed but no banner rendered — this is the silent-degradation bug"
    assert i18n.t("sec_picks") in text, f"banner does not name the failed section: {text!r}"
    assert i18n.t("reason_credit") in text, f"banner does not state the cause: {text!r}"


def test_clean_run_renders_no_banner():
    """No failures must mean no banner — a false alarm every day would be ignored."""
    degradation.reset()
    assert _banner_text(degradation.failures()) == ""


def test_repeated_batch_failures_collapse():
    """
    News is analyzed in batches, so one outage raises once per batch — 169 times
    during the September outage. All of them share a cause and must read as one line.
    """
    degradation.reset()
    for _ in range(169):
        degradation.record("news", CREDIT_ERROR)
    assert degradation.failures() == [("news", "reason_credit")]
    text = _banner_text(degradation.failures())
    assert text.count(i18n.t("sec_news")) == 1, f"section named more than once: {text!r}"


def test_reset_prevents_leak_between_runs():
    """
    The launchd process lives for weeks across many runs. Without a per-run reset,
    a failure on day one would be reported in every later email.
    """
    degradation.reset()
    degradation.record("news", CREDIT_ERROR)
    degradation.reset()
    assert degradation.failures() == []
    assert _banner_text(degradation.failures()) == ""


def test_causes_are_distinguished():
    """Network blips and a dead credit balance need different reader responses."""
    degradation.reset()
    degradation.record("news", CREDIT_ERROR)
    degradation.record("flow", Exception("Connection error."))
    reasons = {reason for _, reason in degradation.failures()}
    assert reasons == {"reason_credit", "reason_network"}, reasons


def test_banner_renders_in_both_languages():
    """The banner is the one section a reader sees only when something is wrong."""
    original = i18n.language()
    try:
        for lang in ("en", "zh"):
            i18n.set_language(lang)
            degradation.reset()
            degradation.record("news", CREDIT_ERROR)
            text = _banner_text(degradation.failures())
            assert i18n.t("degraded_title") in text, f"{lang}: missing title"
            assert i18n.t("sec_news") in text, f"{lang}: missing section name"
            assert "{" not in text, f"{lang}: unsubstituted placeholder in {text!r}"
    finally:
        i18n.set_language(original)
        degradation.reset()


if __name__ == "__main__":
    failures = 0
    tests = [
        test_failure_is_visible_in_email,
        test_clean_run_renders_no_banner,
        test_repeated_batch_failures_collapse,
        test_reset_prevents_leak_between_runs,
        test_causes_are_distinguished,
        test_banner_renders_in_both_languages,
    ]
    for fn in tests:
        try:
            fn()
            print(f"PASS: {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL: {fn.__name__}\n    {e}")
    sys.exit(1 if failures else 0)
