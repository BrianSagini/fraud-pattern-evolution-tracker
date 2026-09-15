"""Lightweight dataframe validation shared by all four DAGs.

Deliberately not a dependency on Great Expectations or pandera: the checks
each pipeline needs (required columns, non-null keys, numeric ranges,
allowed categories) are simple enough that a small dependency-free helper
is easier to reason about than a heavy framework, and every DAG's
validate_* task needs to fail loudly and specifically rather than pass
a green checkmark for the wrong reason.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ValidationReport:
    total_rows: int
    valid_rows: int
    errors: list[str] = field(default_factory=list)
    invalid_row_indices: set[int] = field(default_factory=set)

    @property
    def is_valid(self) -> bool:
        return not self.errors and len(self.invalid_row_indices) == 0

    def raise_if_invalid(self, max_invalid_ratio: float = 0.0) -> None:
        invalid_ratio = len(self.invalid_row_indices) / self.total_rows if self.total_rows else 0
        if self.errors:
            raise ValueError(f"Validation failed: {self.errors}")
        if invalid_ratio > max_invalid_ratio:
            raise ValueError(
                f"Validation failed: {invalid_ratio:.1%} of rows invalid "
                f"(threshold {max_invalid_ratio:.1%}). "
                f"{len(self.invalid_row_indices)}/{self.total_rows} rows quarantined."
            )


def validate_dataframe(
    df: pd.DataFrame,
    *,
    required_columns: list[str],
    not_null_columns: list[str] | None = None,
    numeric_ranges: dict[str, tuple[float, float]] | None = None,
    allowed_values: dict[str, set] | None = None,
) -> ValidationReport:
    errors: list[str] = []
    invalid_rows: set[int] = set()

    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        errors.append(f"missing required columns: {missing}")
        return ValidationReport(total_rows=len(df), valid_rows=0, errors=errors)

    for col in not_null_columns or []:
        invalid_rows |= set(df.index[df[col].isna()])

    for col, (lo, hi) in (numeric_ranges or {}).items():
        out_of_range = df.index[(df[col] < lo) | (df[col] > hi) | df[col].isna()]
        invalid_rows |= set(out_of_range)

    for col, allowed in (allowed_values or {}).items():
        invalid_rows |= set(df.index[~df[col].isin(allowed)])

    return ValidationReport(
        total_rows=len(df),
        valid_rows=len(df) - len(invalid_rows),
        errors=errors,
        invalid_row_indices=invalid_rows,
    )
