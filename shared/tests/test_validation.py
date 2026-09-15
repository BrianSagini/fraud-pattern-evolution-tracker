import pandas as pd

from shared.validation import validate_dataframe


def test_missing_required_columns_reported():
    df = pd.DataFrame({"a": [1, 2]})
    report = validate_dataframe(df, required_columns=["a", "b"])
    assert not report.is_valid
    assert "missing required columns" in report.errors[0]


def test_not_null_check_flags_nulls():
    df = pd.DataFrame({"a": [1, None, 3]})
    report = validate_dataframe(df, required_columns=["a"], not_null_columns=["a"])
    assert report.valid_rows == 2
    assert 1 in report.invalid_row_indices


def test_numeric_range_check():
    df = pd.DataFrame({"temp": [-100, 20, 150]})
    report = validate_dataframe(df, required_columns=["temp"], numeric_ranges={"temp": (-60, 60)})
    assert report.valid_rows == 1
    assert report.invalid_row_indices == {0, 2}


def test_allowed_values_check():
    df = pd.DataFrame({"status": ["ok", "bad", "ok"]})
    report = validate_dataframe(df, required_columns=["status"], allowed_values={"status": {"ok"}})
    assert report.invalid_row_indices == {1}


def test_raise_if_invalid_respects_threshold():
    df = pd.DataFrame({"a": [1, None]})
    report = validate_dataframe(df, required_columns=["a"], not_null_columns=["a"])
    report.raise_if_invalid(max_invalid_ratio=0.5)  # 50% invalid, threshold 50% -> ok
    try:
        report.raise_if_invalid(max_invalid_ratio=0.1)
        assert False, "expected ValueError"
    except ValueError:
        pass
