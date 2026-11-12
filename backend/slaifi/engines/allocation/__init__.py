"""Allocation maths: statistics from real prices, bounds from the strategy, independent re-check."""

from slaifi.engines.allocation.calculations import (
    MIN_RETURN_OBSERVATIONS,
    PERIODS_PER_YEAR,
    AllocationCheck,
    aligned_returns,
    allocation_bounds,
    annualised_statistics,
    portfolio_statistics,
    return_preference,
    verify_allocation,
)

__all__ = [
    "MIN_RETURN_OBSERVATIONS",
    "PERIODS_PER_YEAR",
    "AllocationCheck",
    "aligned_returns",
    "allocation_bounds",
    "annualised_statistics",
    "portfolio_statistics",
    "return_preference",
    "verify_allocation",
]
