"""Tier classification.

Assigns a cost tier (T0-T4) and a SWaP tier (S0-S4) to each system from
its own figures, so tiers cannot drift out of sync with the catalog.
"""

from __future__ import annotations

from typing import Final

from .models import Classification, CostTier, Equipment, SwapTier, Taxonomy

FALLBACK_COST_TIER: Final[str] = "T4"
FALLBACK_SWAP_TIER: Final[str] = "S4"
TIER_LABEL_LENGTH: Final[int] = 2
UNRANKED: Final[int] = 99


def classify_cost(unit_cost_usd: float, tiers: tuple[CostTier, ...]) -> CostTier:
    """Return the lowest cost tier whose ceiling the unit cost fits under."""
    for tier in tiers:
        if unit_cost_usd <= tier.max_unit_cost_usd:
            return tier
    return tiers[-1]


def classify_swap(weight_lb: float, power_w: float, tiers: tuple[SwapTier, ...]) -> SwapTier:
    """Return the lowest SWaP tier satisfying both weight and power limits."""
    for tier in tiers:
        if weight_lb <= tier.max_weight_lb and power_w <= tier.max_power_w:
            return tier
    return tiers[-1]


def classify(item: Equipment, taxonomy: Taxonomy) -> Classification:
    """Assign both tier labels and carry forward the posture guidance."""
    cost_tier: CostTier = classify_cost(item.swap_c.unit_cost_usd, taxonomy.cost_tiers)
    swap_tier: SwapTier = classify_swap(
        item.swap_c.weight_lb, item.swap_c.power_w, taxonomy.swap_tiers
    )
    return Classification(
        cost_tier=cost_tier.tier,
        cost_tier_name=cost_tier.name,
        swap_tier=swap_tier.tier,
        swap_tier_name=swap_tier.name,
        attritability=cost_tier.attritability,
        emplacement=swap_tier.emplacement,
        acquisition_note=cost_tier.acquisition_note,
    )


def tier_rank(tier: str) -> int:
    """Return the numeric rank of a tier label for ordering and ceilings."""
    if len(tier) < TIER_LABEL_LENGTH or not tier[1:].isdigit():
        return UNRANKED
    return int(tier[1:])


def within_ceiling(assigned_tier: str, ceiling_tier: str) -> bool:
    """True when the assigned tier is at or below the requested ceiling."""
    return tier_rank(assigned_tier) <= tier_rank(ceiling_tier)
