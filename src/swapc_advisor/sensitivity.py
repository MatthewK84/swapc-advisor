"""Deterministic sensitivity analysis.

A third of catalog costs are order-of-magnitude placeholders and every Pk
is an assumption, so a point-estimate ranking overstates certainty. This
module perturbs cost by +/-50% and Pk by +/-0.15 on a fixed 3x3 grid,
re-ranks under each scenario, and reports whether the top pick survives.
The grid is deterministic, not sampled, so results are reproducible on
air-gapped hosts and in CI.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Final

from .models import Equipment, ScoredCandidate, SensitivityResult, SwapC

if TYPE_CHECKING:
    from collections.abc import Callable

COST_FACTORS: Final[tuple[float, ...]] = (0.5, 1.0, 1.5)
PK_SHIFTS: Final[tuple[float, ...]] = (-0.15, 0.0, 0.15)
PK_FLOOR: Final[float] = 0.05
PK_CEILING: Final[float] = 0.98
STABILITY_THRESHOLD: Final[float] = 2.0 / 3.0

Scorer = "Callable[[Equipment], ScoredCandidate]"


def perturb(item: Equipment, cost_factor: float, pk_shift: float) -> Equipment:
    """Return a copy of the item with cost scaled and Pk shifted."""
    new_swap: SwapC = replace(item.swap_c, unit_cost_usd=item.swap_c.unit_cost_usd * cost_factor)
    new_pk: dict[int, float] = {
        group: min(PK_CEILING, max(PK_FLOOR, pk + pk_shift))
        for group, pk in item.single_shot_pk.items()
    }
    return replace(item, swap_c=new_swap, single_shot_pk=new_pk)


def _rank_ids(
    items: tuple[Equipment, ...], score: Callable[[Equipment], ScoredCandidate]
) -> tuple[str, ...]:
    """Score every item and return equipment ids best-first."""
    scored: list[ScoredCandidate] = [score(item) for item in items]
    passing: list[ScoredCandidate] = [c for c in scored if c.hard_pass]
    passing.sort(key=lambda c: c.total_score, reverse=True)
    return tuple(c.equipment.equipment_id for c in passing)


def _stability_note(top_id: str, wins: int, scenarios: int, stable: bool) -> str:
    """Plain-language reading of the stability result."""
    if stable:
        return (
            f"{top_id} holds rank 1 in {wins} of {scenarios} perturbation "
            f"scenarios. The recommendation is robust to the stated data "
            f"uncertainty."
        )
    return (
        f"{top_id} holds rank 1 in only {wins} of {scenarios} scenarios. "
        f"Given cost and Pk uncertainty, the top candidates are statistically "
        f"indistinguishable. Treat them as a trade space, not a decision, "
        f"until vendor quotes and test data narrow the inputs."
    )


def analyze_sensitivity(
    items: tuple[Equipment, ...],
    baseline_top_id: str,
    score: Callable[[Equipment], ScoredCandidate],
) -> SensitivityResult:
    """Re-rank under every grid scenario and summarize rank stability."""
    scenarios: int = 0
    top_wins: int = 0
    ranges: dict[str, tuple[int, int]] = {}
    for cost_factor in COST_FACTORS:
        for pk_shift in PK_SHIFTS:
            scenarios += 1
            perturbed: tuple[Equipment, ...] = tuple(
                perturb(item, cost_factor, pk_shift) for item in items
            )
            order: tuple[str, ...] = _rank_ids(perturbed, score)
            if order and order[0] == baseline_top_id:
                top_wins += 1
            for position, equipment_id in enumerate(order, start=1):
                low, high = ranges.get(equipment_id, (position, position))
                ranges[equipment_id] = (min(low, position), max(high, position))
    stable: bool = scenarios > 0 and (top_wins / scenarios) >= STABILITY_THRESHOLD
    return SensitivityResult(
        scenarios=scenarios,
        top_pick_id=baseline_top_id,
        top_pick_wins=top_wins,
        stable=stable,
        rank_ranges=ranges,
        notes=_stability_note(baseline_top_id, top_wins, scenarios, stable),
    )
