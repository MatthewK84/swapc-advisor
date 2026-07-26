"""Cost-exchange economics.

Unit cost alone misranks C-UAS effectors. A recoverable interceptor
amortizes across sorties, a jammer across thousands of engagements, and a
low-Pk round needs several attempts per defeat. This module reduces all of
that to one comparable figure: cost per defeat, and its ratio against
threat cost.
"""

from __future__ import annotations

import math
from typing import Final

from .models import Aor, Equipment, ExchangeAnalysis, MissionThread, UasGroup

MIN_PK: Final[float] = 0.05
MAX_ROUNDS_PER_DEFEAT: Final[float] = 20.0
DAYS_PER_MONTH: Final[float] = 30.0
FAVORABLE_RATIO: Final[float] = 1.0
STRONG_RATIO: Final[float] = 10.0
ASSET_DAMAGE_PROBABILITY: Final[float] = 0.25
GOOD_RATIO: Final[float] = 3.0
ENABLER_NEUTRAL_SCORE: Final[float] = 0.5


def is_enabler(item: Equipment) -> bool:
    """True for sensors and C2 that detect or track but do not defeat."""
    return not item.single_shot_pk or all(v <= 0.0 for v in item.single_shot_pk.values())


def effective_pk(item: Equipment, thread: MissionThread) -> float:
    """Conservative Pk: the minimum across groups this thread engages.

    A round that is 0.7 against a hovering quadcopter is not 0.7 against a
    Shahed closing at 185 km/h, so planning uses the worst relevant case.
    """
    if is_enabler(item):
        return 0.0
    relevant: tuple[float, ...] = tuple(
        item.single_shot_pk[g] for g in thread.target_groups if g in item.single_shot_pk
    )
    if relevant:
        return min(relevant)
    return min(item.single_shot_pk.values())


def rounds_per_defeat(item: Equipment, thread: MissionThread) -> float:
    """Expected rounds per defeat, from the worst relevant per-group Pk."""
    if is_enabler(item):
        return 0.0
    pk: float = max(effective_pk(item, thread), MIN_PK)
    return min(1.0 / pk, MAX_ROUNDS_PER_DEFEAT)


def effective_round_cost(item: Equipment) -> float:
    """Unit cost amortized across the number of uses the system supports."""
    uses: int = max(item.uses_per_unit, 1)
    return item.swap_c.unit_cost_usd / uses


def cost_per_defeat(item: Equipment, thread: MissionThread) -> float:
    """Total effector cost to achieve one defeat."""
    if is_enabler(item):
        return 0.0
    return effective_round_cost(item) * rounds_per_defeat(item, thread)


def threat_cost_for(thread: MissionThread, aor: Aor, groups: tuple[UasGroup, ...]) -> float:
    """Median threat cost for the groups this thread targets in this AOR.

    Uses the lower of the AOR median and the targeted-group median, because
    the cheapest credible threat sets the exchange bar an effector must clear.
    """
    relevant: tuple[float, ...] = tuple(
        g.median_threat_cost_usd for g in groups if g.group in thread.target_groups
    )
    if not relevant:
        return aor.median_threat_cost_usd
    return min(aor.median_threat_cost_usd, *relevant)


def _replenish_days(item: Equipment, magazine_rounds: float) -> float:
    """Days of production needed to rebuild the magazine at stated rate."""
    if item.units_per_month <= 0:
        return math.inf
    per_day: float = item.units_per_month / DAYS_PER_MONTH
    return magazine_rounds / per_day


def _exchange_note(item: Equipment, ratio: float, threat_cost: float) -> str:
    """Plain-language reading of the exchange result."""
    if is_enabler(item):
        return (
            "Enabler, not an effector. Contributes detection and cueing, so "
            "exchange ratio does not apply. Its value is enabling cheaper "
            "effectors to be employed at all."
        )
    if ratio >= STRONG_RATIO:
        return f"Strongly favorable. Each defeat costs about 1/{ratio:.0f} of the threat."
    if ratio >= GOOD_RATIO:
        return f"Favorable at {ratio:.1f}:1 against a ${threat_cost:,.0f} threat."
    if ratio >= FAVORABLE_RATIO:
        return f"Marginally favorable at {ratio:.1f}:1. Thin margin against cheaper threats."
    return (
        f"Unfavorable at {ratio:.2f}:1. Each defeat costs more than the "
        f"${threat_cost:,.0f} threat it removes, which cannot be sustained "
        f"against mass attack."
    )


def analyze_exchange(
    item: Equipment,
    thread: MissionThread,
    aor: Aor,
    groups: tuple[UasGroup, ...],
    asset_value_usd: float = 0.0,
) -> ExchangeAnalysis:
    """Full cost-exchange analysis of one system for one mission and AOR.

    When asset_value_usd is supplied, the exchange numerator becomes the
    value denied: threat cost plus expected damage prevented, modeled as
    asset value times ASSET_DAMAGE_PROBABILITY. Defeating a $3K FPV that
    would mission-kill a $40M aircraft is worth far more than $3K.
    """
    threat_cost: float = threat_cost_for(thread, aor, groups)
    value_denied: float = threat_cost + asset_value_usd * ASSET_DAMAGE_PROBABILITY
    per_defeat: float = cost_per_defeat(item, thread)
    ratio: float = 0.0
    if per_defeat > 0.0:
        ratio = value_denied / per_defeat
    rounds: float = rounds_per_defeat(item, thread)
    magazine_rounds: float = max(rounds * thread.typical_salvo_size, 1.0)
    magazine_cost: float = magazine_rounds * effective_round_cost(item)
    if is_enabler(item):
        magazine_rounds = 1.0
        magazine_cost = item.swap_c.unit_cost_usd
    return ExchangeAnalysis(
        rounds_per_defeat=round(rounds, 2),
        cost_per_defeat_usd=round(per_defeat, 2),
        threat_cost_usd=value_denied,
        exchange_ratio=round(ratio, 3),
        favorable=ratio >= FAVORABLE_RATIO,
        magazine_rounds=int(math.ceil(magazine_rounds)),
        magazine_cost_usd=round(magazine_cost, 2),
        replenish_days=round(_replenish_days(item, magazine_rounds), 2),
        notes=_exchange_note(item, ratio, value_denied),
    )


def exchange_score(analysis: ExchangeAnalysis, item: Equipment, target: float) -> float:
    """Normalize exchange ratio to 0-1 on a log scale against the target."""
    if is_enabler(item):
        return ENABLER_NEUTRAL_SCORE
    if analysis.exchange_ratio <= FAVORABLE_RATIO:
        return 0.0
    ceiling: float = max(target, 2.0)
    raw: float = math.log10(analysis.exchange_ratio) / math.log10(ceiling)
    return min(1.0, max(0.0, raw))
