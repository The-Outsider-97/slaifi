"""Allocation suggestions (optional SLAI Financial agent) and applying them as paper orders."""

from slaifi.application.allocation.service import (
    AllocationLine,
    AllocationService,
    AllocationStats,
    AllocationSuggestion,
    AppliedAllocation,
    AppliedOrder,
)

__all__ = [
    "AllocationLine",
    "AllocationService",
    "AllocationStats",
    "AllocationSuggestion",
    "AppliedAllocation",
    "AppliedOrder",
]
