"""Down-selection engine.

Scoring is inverted relative to a conventional trade study. Cost exchange
and SWaP efficiency carry the most weight; fielding maturity is a modest
discipline term rather than the dominant factor. Program-of-record systems
are separated into a baseline set so they inform the comparison without
crowding out attritable options.
"""

from __future__ import annotations

import math
from typing import Final

from .cost_model import analyze_exchange, exchange_score, is_enabler
from .knowledge_base import KnowledgeBase, build_corpus
from .models import (
    Aor,
    Classification,
    Equipment,
    ExchangeAnalysis,
    MissionThread,
    Posture,
    Query,
    Recommendation,
    RetrievedDoc,
    ScoredCandidate,
    UasGroup,
    ValidationError,
)
from .retriever import HybridRetriever
from .taxonomy import classify, within_ceiling

TOP_CONTEXT_DOCS: Final[int] = 8
SWAP_MIN_LB: Final[float] = 1.0
SWAP_MAX_LB: Final[float] = 20000.0
POWER_MAX_W: Final[float] = 50000.0
RATE_TARGET_PER_MONTH: Final[float] = 3000.0
REPLENISH_WARN_DAYS: Final[float] = 30.0
HIGH_RATE_PER_MONTH: Final[int] = 1000
NON_FLYING_TYPES: Final[frozenset[str]] = frozenset(
    {
        "handheld_ew",
        "wearable_ew",
        "smart_optic_kinetic",
        "sensor_fusion_c2",
        "passive_acoustic_sensor",
        "esa_radar",
        "high_power_microwave",
        "vehicle_layered_defeat",
        "radar_c2_layered",
        "guided_rocket",
        "low_cost_missile",
    }
)


def validate_query(kb: KnowledgeBase, query: Query) -> tuple[Aor, MissionThread, Posture]:
    """Validate the query against the KB, returning resolved references."""
    if query.cost_threshold_usd <= 0:
        raise ValidationError("Cost threshold must be positive.")
    if query.flight_time_min < 0 or query.distance_km < 0:
        raise ValidationError("Flight time and distance cannot be negative.")
    aor: Aor | None = kb.find_aor(query.aor_id)
    if aor is None:
        raise ValidationError(
            f"Unknown AOR '{query.aor_id}'. Valid: {', '.join(a.aor_id for a in kb.aors)}"
        )
    thread: MissionThread | None = kb.find_thread(query.mission_thread_id)
    if thread is None:
        raise ValidationError(
            f"Unknown mission thread '{query.mission_thread_id}'. Valid: "
            f"{', '.join(t.thread_id for t in kb.mission_threads)}"
        )
    posture: Posture | None = kb.taxonomy.find_posture(query.posture_id)
    if posture is None:
        raise ValidationError(
            f"Unknown posture '{query.posture_id}'. Valid: "
            f"{', '.join(p.posture_id for p in kb.taxonomy.postures)}"
        )
    return aor, thread, posture


def _is_flight_exempt(item: Equipment) -> bool:
    """True for ground-based systems where flight metrics do not apply."""
    return item.system_type in NON_FLYING_TYPES or item.flight_time_min <= 0.0


def _apply_hard_gates(
    item: Equipment, query: Query, classification: Classification
) -> tuple[str, ...]:
    """Return disqualifier strings; empty tuple means the item passes."""
    fails: list[str] = []
    if item.swap_c.unit_cost_usd > query.cost_threshold_usd:
        fails.append(
            f"Unit cost ${item.swap_c.unit_cost_usd:,.0f} exceeds threshold "
            f"${query.cost_threshold_usd:,.0f}"
        )
    if not within_ceiling(classification.cost_tier, query.max_cost_tier):
        fails.append(
            f"Cost tier {classification.cost_tier} exceeds requested ceiling {query.max_cost_tier}"
        )
    if _is_flight_exempt(item):
        return tuple(fails)
    if item.flight_time_min < query.flight_time_min:
        fails.append(
            f"Flight time {item.flight_time_min:.0f} min below required "
            f"{query.flight_time_min:.0f} min"
        )
    if item.effective_range_km < query.distance_km:
        fails.append(
            f"Range {item.effective_range_km:.0f} km below required {query.distance_km:.0f} km"
        )
    return tuple(fails)


def _score_thread(item: Equipment, thread: MissionThread) -> float:
    """1.0 for a listed thread match, 0.4 for same category, else 0."""
    if thread.thread_id in item.mission_threads:
        return 1.0
    if item.category == thread.category:
        return 0.4
    return 0.0


def _score_aor(item: Equipment, aor: Aor) -> float:
    """Environment overlap plus EW and GNSS suitability, capped at 1.0."""
    overlap: int = len(set(item.environment_tags) & set(aor.environment_tags))
    env: float = min(overlap / 3.0, 1.0) * 0.5
    contested: bool = aor.ew_environment in {"contested", "highly_contested"}
    ew: float = 0.25 if (item.ew_resilient or not contested) else 0.0
    degraded: bool = aor.gps_environment in {"degraded", "denied", "intermittent"}
    gps: float = 0.25 if (item.gps_denied_capable or not degraded) else 0.0
    return env + ew + gps


def _score_groups(item: Equipment, aor: Aor, thread: MissionThread) -> float:
    """Fraction of thread-and-AOR-relevant threat groups the system covers."""
    relevant: set[int] = set(thread.target_groups) & set(aor.dominant_threat_groups)
    if not relevant:
        relevant = set(thread.target_groups)
    return len(relevant & set(item.target_groups)) / len(relevant)


def _score_swap(item: Equipment) -> float:
    """Reward low weight and power on a log scale. Lighter scores higher."""
    weight: float = max(item.swap_c.weight_lb, SWAP_MIN_LB)
    weight_score: float = 1.0 - (
        math.log10(weight / SWAP_MIN_LB) / math.log10(SWAP_MAX_LB / SWAP_MIN_LB)
    )
    power: float = max(item.swap_c.power_w, 1.0)
    power_score: float = 1.0 - (math.log10(power) / math.log10(POWER_MAX_W))
    return max(0.0, min(1.0, 0.6 * weight_score + 0.4 * power_score))


def _score_production(item: Equipment) -> float:
    """Reward monthly production rate on a log scale against a target."""
    if item.units_per_month <= 0:
        return 0.0
    raw: float = math.log10(item.units_per_month) / math.log10(RATE_TARGET_PER_MONTH)
    return max(0.0, min(1.0, raw))


def _watch_items(item: Equipment, exchange: ExchangeAnalysis) -> tuple[str, ...]:
    """Risks a planner must resolve before programming against this system."""
    items: list[str] = []
    if item.cost_confidence == "order_of_magnitude":
        items.append(
            f"Cost is an order-of-magnitude placeholder ({item.as_of}), not a quote. "
            f"Source: {item.source_note}"
        )
    if item.evidence_grade in {"development", "concept"}:
        items.append(
            f"Evidence grade is {item.evidence_grade}. Performance claims are "
            f"unverified; do not program against these figures."
        )
    if item.vendor_maturity == "startup":
        items.append(
            "Startup vendor. Confirm production capacity, financial runway, and "
            "second-source options before committing to a magazine."
        )
    if not is_enabler(item) and not exchange.favorable:
        items.append(
            f"Unfavorable cost exchange at {exchange.exchange_ratio:.2f}:1 against "
            f"a ${exchange.threat_cost_usd:,.0f} threat."
        )
    if exchange.replenish_days > REPLENISH_WARN_DAYS:
        items.append(
            f"Magazine replenishment takes {exchange.replenish_days:.0f} days at "
            f"stated production rate. Sustained engagement will outpace supply."
        )
    return tuple(items)


def _rationale(item: Equipment, cls: Classification, exchange: ExchangeAnalysis) -> tuple[str, ...]:
    """Short human-readable reasons for the ranking."""
    reasons: list[str] = [
        f"{cls.cost_tier} {cls.cost_tier_name} / {cls.swap_tier} {cls.swap_tier_name}"
    ]
    if not is_enabler(item):
        reasons.append(
            f"${exchange.cost_per_defeat_usd:,.0f} per defeat, "
            f"{exchange.exchange_ratio:.1f}:1 exchange"
        )
    reasons.append(exchange.notes)
    if item.units_per_month >= HIGH_RATE_PER_MONTH:
        reasons.append(f"Production {item.units_per_month:,}/month supports magazine depth")
    if item.evidence_grade == "combat_proven":
        reasons.append("Combat-proven employment")
    reasons.append(item.notes)
    return tuple(reasons)


def _score_candidate(
    item: Equipment,
    *,
    query: Query,
    aor: Aor,
    thread: MissionThread,
    posture: Posture,
    kb: KnowledgeBase,
) -> ScoredCandidate:
    """Apply hard gates, compute economics, then the weighted posture score."""
    cls: Classification = classify(item, kb.taxonomy)
    exchange: ExchangeAnalysis = analyze_exchange(item, thread, aor, kb.uas_groups)
    weights: dict[str, float] = posture.weights
    evidence: float = kb.taxonomy.evidence_confidence.get(item.evidence_grade, 0.3)
    breakdown: dict[str, float] = {
        "exchange": exchange_score(exchange, item, thread.exchange_ratio_target)
        * weights["exchange"],
        "swap": _score_swap(item) * weights["swap"],
        "thread": _score_thread(item, thread) * weights["thread"],
        "aor": _score_aor(item, aor) * weights["aor"],
        "groups": _score_groups(item, aor, thread) * weights["groups"],
        "production": _score_production(item) * weights["production"],
        "evidence": evidence * weights["evidence"],
    }
    multiplier: float = posture.tier_multipliers.get(cls.cost_tier, 1.0)
    total: float = sum(breakdown.values()) * multiplier
    return ScoredCandidate(
        equipment=item,
        classification=cls,
        exchange=exchange,
        total_score=round(total, 4),
        tier_multiplier=multiplier,
        hard_pass=not _apply_hard_gates(item, query, cls),
        score_breakdown=breakdown,
        rationale=_rationale(item, cls, exchange),
        disqualifiers=_apply_hard_gates(item, query, cls),
        watch_items=_watch_items(item, exchange),
    )


def _retrieve_context(
    kb: KnowledgeBase, query: Query, aor: Aor, thread: MissionThread
) -> tuple[RetrievedDoc, ...]:
    """Run the RAG retrieval pass for report grounding."""
    retriever: HybridRetriever = HybridRetriever(build_corpus(kb))
    search_text: str = (
        f"{thread.name} {thread.description} attritable low cost exchange "
        f"economics magazine depth {aor.name} {aor.threat_profile} "
        f"{aor.exchange_context} flight {query.flight_time_min} minutes range "
        f"{query.distance_km} km under ${query.cost_threshold_usd:,.0f}"
    )
    return retriever.search(search_text, top_k=TOP_CONTEXT_DOCS)


def _summary(
    *,
    query: Query,
    aor: Aor,
    thread: MissionThread,
    posture: Posture,
    ranked: tuple[ScoredCandidate, ...],
    enablers: tuple[ScoredCandidate, ...],
    baselines: tuple[ScoredCandidate, ...],
) -> str:
    """BLUF summary paragraph anchored on cost exchange, not unit cost."""
    if not ranked:
        return (
            f"BLUF: No cataloged system meets all thresholds for {thread.name} in "
            f"{aor.aor_id} under posture {posture.name}. Relax the "
            f"${query.cost_threshold_usd:,.0f} ceiling, the "
            f"{query.flight_time_min:.0f} min / {query.distance_km:.0f} km flight "
            f"requirement, or the {query.max_cost_tier} tier ceiling."
        )
    top: ScoredCandidate = ranked[0]
    delta: str = ""
    if baselines:
        base: ScoredCandidate = baselines[0]
        if base.exchange.cost_per_defeat_usd > 0 and top.exchange.cost_per_defeat_usd > 0:
            factor: float = base.exchange.cost_per_defeat_usd / top.exchange.cost_per_defeat_usd
            delta = (
                f" Against the {base.equipment.name} baseline it is {factor:.1f}x "
                f"cheaper per defeat (${top.exchange.cost_per_defeat_usd:,.0f} versus "
                f"${base.exchange.cost_per_defeat_usd:,.0f})."
            )
    alternates: str = ", ".join(c.equipment.name for c in ranked[1:3])
    alt: str = f" Alternate effectors: {alternates}." if alternates else ""
    cue: str = ""
    if enablers:
        cue = (
            f" Pair with {enablers[0].equipment.name} at "
            f"${enablers[0].equipment.swap_c.unit_cost_usd:,.0f} per node for "
            f"detection and cueing; attritable effectors need an external sensor "
            f"picture to be employable."
        )
    return (
        f"BLUF: {top.equipment.name} is the primary recommendation for "
        f"{thread.name} in {aor.aor_id}, classified "
        f"{top.classification.cost_tier} {top.classification.cost_tier_name} / "
        f"{top.classification.swap_tier} {top.classification.swap_tier_name} at "
        f"${top.equipment.swap_c.unit_cost_usd:,.0f} per unit. Cost per defeat is "
        f"${top.exchange.cost_per_defeat_usd:,.0f} for a "
        f"{top.exchange.exchange_ratio:.1f}:1 exchange against a "
        f"${top.exchange.threat_cost_usd:,.0f} threat.{delta}{alt}{cue}"
    )


def _tier_distribution(candidates: tuple[ScoredCandidate, ...]) -> dict[str, int]:
    """Count of passing candidates per cost tier."""
    counts: dict[str, int] = {}
    for cand in candidates:
        tier: str = cand.classification.cost_tier
        counts[tier] = counts.get(tier, 0) + 1
    return counts


def recommend(kb: KnowledgeBase, query: Query) -> Recommendation:
    """Produce the full ranked recommendation for one validated query."""
    aor, thread, posture = validate_query(kb, query)
    scored: tuple[ScoredCandidate, ...] = tuple(
        _score_candidate(item, query=query, aor=aor, thread=thread, posture=posture, kb=kb)
        for item in kb.equipment
    )
    relevant: tuple[ScoredCandidate, ...] = tuple(
        c for c in scored if thread.thread_id in c.equipment.mission_threads
    )
    passing: list[ScoredCandidate] = [c for c in relevant if c.hard_pass]
    passing.sort(key=lambda c: c.total_score, reverse=True)
    selectable: tuple[ScoredCandidate, ...] = tuple(
        c for c in passing if not c.equipment.baseline_comparator
    )
    ranked: tuple[ScoredCandidate, ...] = tuple(
        c for c in selectable if not is_enabler(c.equipment)
    )
    enablers: tuple[ScoredCandidate, ...] = tuple(c for c in selectable if is_enabler(c.equipment))
    baselines: tuple[ScoredCandidate, ...] = tuple(
        c for c in relevant if c.equipment.baseline_comparator
    )
    rejected: list[ScoredCandidate] = [c for c in relevant if not c.hard_pass]
    rejected.sort(key=lambda c: c.total_score, reverse=True)
    groups: tuple[UasGroup, ...] = kb.groups_by_number(thread.target_groups)
    return Recommendation(
        query=query,
        posture=posture,
        aor=aor,
        thread=thread,
        relevant_groups=groups,
        ranked=ranked,
        enablers=enablers,
        baselines=baselines,
        rejected=tuple(rejected),
        retrieved_context=_retrieve_context(kb, query, aor, thread),
        tier_distribution=_tier_distribution(ranked),
        summary=_summary(
            query=query,
            aor=aor,
            thread=thread,
            posture=posture,
            ranked=ranked,
            enablers=enablers,
            baselines=baselines,
        ),
    )
