import itertools

import pytest

from app.modules.auth.email_identity_verifier import (
    EmailIdentityVerifier, VerificationReport, _Sort, _bound, _expected,
)
from app.modules.auth.email_identity_backfill import MaintenanceRequired


@pytest.mark.parametrize("value", [0, -1, 1001, True, None, 1.5, "500"])
def test_reject_unbounded_batches(value):
    with pytest.raises(ValueError):
        _bound(value)


def test_requires_established_context():
    with pytest.raises(MaintenanceRequired):
        EmailIdentityVerifier(object())


@pytest.mark.parametrize("batch", [1, 2, 17, 500])
def test_external_merge_and_independent_owner_reduction(tmp_path, batch):
    # More than FAN_IN squared runs at batch=1 exercises multiple merge levels.
    rows = [(f"x{i:04}@example.test", "a", False) for i in range(300)]
    rows += [("x0000@example.test", "b", False), ("x0001@example.test", "a", True)]
    sorter = _Sort(tmp_path, batch)
    for row in reversed(rows):
        sorter.add(row)
    actual = list(_expected(sorter.rows()))
    assert len(actual) == 300
    assert actual[:2] == [("x0000@example.test", "blocked", None, 1), ("x0001@example.test", "blocked", None, 1)]
    assert all(row[1:] == ("owned", "a", 1) for row in actual[2:])
    assert all(p.stat().st_mode & 0o077 == 0 for p in tmp_path.iterdir())


def test_order_independent_blocking_and_repeated_same_owner():
    rows = [("a@b.test", "a", False), ("a@b.test", "a", False), ("a@b.test", "b", False)]
    for order in itertools.permutations(rows):
        assert list(_expected(sorted(order))) == [("a@b.test", "blocked", None, 1)]
    assert list(_expected(sorted(rows[:2]))) == [("a@b.test", "owned", "a", 1)]


def test_empty_sort(tmp_path):
    assert list(_expected(_Sort(tmp_path, 1).rows())) == []


def test_report_fails_closed():
    report = VerificationReport(0, 0, 0, 0, (("source_count", 1),), "a", "b", "c", "d")
    assert not report.passed
