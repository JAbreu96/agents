"""Unit tests for src/job_digest.py — no network calls."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from src.job_digest import classify_status, compute_stats, build_digest


def _row(title="Engineer", date_added=None, date_applied=""):
    if date_added is None:
        date_added = date.today().strftime("%Y-%m-%d")
    return {
        "title": title,
        "summary": "",
        "link": "https://example.com",
        "date_added": date_added,
        "contacts": "",
        "notes": "",
        "date_applied": date_applied,
    }


class TestClassifyStatus:
    def test_applied(self):
        row = _row(date_applied="2026-03-20")
        assert classify_status(row) == "applied"

    def test_not_applied_recent(self):
        row = _row(date_added=date.today().strftime("%Y-%m-%d"))
        assert classify_status(row) == "not_applied"

    def test_stale(self):
        old_date = (date.today() - timedelta(days=20)).strftime("%Y-%m-%d")
        row = _row(date_added=old_date)
        assert classify_status(row) == "stale"

    def test_applied_takes_precedence_over_stale(self):
        old_date = (date.today() - timedelta(days=20)).strftime("%Y-%m-%d")
        row = _row(date_added=old_date, date_applied="2026-03-25")
        assert classify_status(row) == "applied"

    def test_empty_date_added_is_not_applied(self):
        row = _row(date_added="")
        assert classify_status(row) == "not_applied"


class TestComputeStats:
    def _make_rows(self):
        today = date.today()
        return [
            _row(date_added=(today - timedelta(days=3)).strftime("%Y-%m-%d"), date_applied=(today - timedelta(days=2)).strftime("%Y-%m-%d")),  # applied, recent
            _row(date_added=(today - timedelta(days=20)).strftime("%Y-%m-%d")),   # stale
            _row(date_added=(today - timedelta(days=20)).strftime("%Y-%m-%d")),   # stale
            _row(date_added=(today - timedelta(days=1)).strftime("%Y-%m-%d")),    # not_applied, recent
            _row(date_added=(today - timedelta(days=5)).strftime("%Y-%m-%d")),    # not_applied, recent
        ]

    def test_counts(self):
        rows = self._make_rows()
        for row in rows:
            row["status"] = classify_status(row)
        stats = compute_stats(rows)
        assert stats["total"] == 5
        assert stats["applied"] == 1
        assert stats["stale"] == 2
        assert stats["not_applied"] == 2

    def test_last_7_days(self):
        rows = self._make_rows()
        for row in rows:
            row["status"] = classify_status(row)
        stats = compute_stats(rows)
        assert stats["added_last_7_days"] == 3   # days 3, 1, 5 are all <=7
        assert stats["applied_last_7_days"] == 1


class TestBuildDigest:
    def test_structure(self):
        fake_rows = [
            _row("Job A", date_added="2026-03-20", date_applied="2026-03-22"),
            _row("Job B", date_added="2026-03-25"),
        ]
        with patch("src.job_digest.get_all_rows", return_value=fake_rows):
            digest = build_digest()

        assert "generated_at" in digest
        assert digest["total_jobs"] == 2
        assert len(digest["rows"]) == 2
        assert "status" in digest["rows"][0]
        assert digest["rows"][0]["status"] == "applied"
        assert "stats" in digest
        assert digest["stats"]["total"] == 2
