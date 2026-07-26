"""Typed domain models for the SWAP-C down-selection advisor.

All models are frozen dataclasses. No mutable module-level state.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class AdvisorError(Exception):
    """Base exception for all advisor failures."""


class KnowledgeBaseError(AdvisorError):
    """Raised when knowledge base files are missing or malformed."""


class ValidationError(AdvisorError):
    """Raised when user query inputs fail validation."""


class ReportError(AdvisorError):
    """Raised when report generation fails."""


@dataclass(frozen=True)
class SwapC:
    """Size, Weight, Power, and Cost figures for one system."""

    weight_lb: float
    size: str
    power_w: float
    unit_cost_usd: float


@dataclass(frozen=True)
class CostTier:
    """One cost-attritability tier definition."""

    tier: str
    name: str
    max_unit_cost_usd: float
    posture: str
    acquisition_note: str
    attritability: float


@dataclass(frozen=True)
class SwapTier:
    """One size, weight, and power portability tier definition."""

    tier: str
    name: str
    max_weight_lb: float
    max_power_w: float
    emplacement: str
    logistics_note: str


@dataclass(frozen=True)
class Posture:
    """One scoring posture profile with weights and tier multipliers."""

    posture_id: str
    name: str
    intent: str
    weights: dict[str, float]
    tier_multipliers: dict[str, float]


@dataclass(frozen=True)
class Taxonomy:
    """Full classification taxonomy loaded from swapc_tiers.json."""

    cost_tiers: tuple[CostTier, ...]
    swap_tiers: tuple[SwapTier, ...]
    evidence_confidence: dict[str, float]
    postures: tuple[Posture, ...]

    def find_posture(self, posture_id: str) -> Posture | None:
        """Return the posture matching the given id."""
        for posture in self.postures:
            if posture.posture_id == posture_id:
                return posture
        return None


@dataclass(frozen=True)
class Equipment:
    """One UAS or C-UAS system in the catalog."""

    equipment_id: str
    name: str
    vendor: str
    vendor_maturity: str
    system_type: str
    category: str
    mission_threads: tuple[str, ...]
    target_groups: tuple[int, ...]
    swap_c: SwapC
    flight_time_min: float
    effective_range_km: float
    single_shot_pk: dict[int, float]
    uses_per_unit: int
    units_per_month: int
    evidence_grade: str
    baseline_comparator: bool
    environment_tags: tuple[str, ...]
    gps_denied_capable: bool
    ew_resilient: bool
    cost_confidence: str
    as_of: str
    source_note: str
    notes: str


@dataclass(frozen=True)
class Classification:
    """Assigned tier labels for one system."""

    cost_tier: str
    cost_tier_name: str
    swap_tier: str
    swap_tier_name: str
    attritability: float
    emplacement: str
    acquisition_note: str


@dataclass(frozen=True)
class ExchangeAnalysis:
    """Cost-exchange economics for one system against one threat set."""

    rounds_per_defeat: float
    cost_per_defeat_usd: float
    threat_cost_usd: float
    exchange_ratio: float
    favorable: bool
    magazine_rounds: int
    magazine_cost_usd: float
    replenish_days: float
    notes: str


@dataclass(frozen=True)
class Aor:
    """One geographic combatant command area of responsibility."""

    aor_id: str
    name: str
    region: str
    environment_tags: tuple[str, ...]
    dominant_threat_groups: tuple[int, ...]
    ew_environment: str
    gps_environment: str
    median_threat_cost_usd: float
    monthly_engagement_estimate: int
    resupply_difficulty: str
    attritability_driver: str
    threat_profile: str
    operating_notes: str
    exchange_context: str


@dataclass(frozen=True)
class MissionThread:
    """One mission thread with its targeted UAS groups and requirements."""

    thread_id: str
    name: str
    category: str
    target_groups: tuple[int, ...]
    typical_salvo_size: int
    exchange_ratio_target: float
    attritability_priority: str
    description: str
    key_requirements: tuple[str, ...]
    engagement_range_km: tuple[float, float]


@dataclass(frozen=True)
class UasGroup:
    """One DoD UAS group with SWAP-C and threat-cost estimates."""

    group: int
    name: str
    max_weight_lb: float
    operating_altitude_ft: float
    max_speed_kt: float
    endurance_min: tuple[float, float]
    range_km: tuple[float, float]
    unit_cost_usd: tuple[float, float]
    median_threat_cost_usd: float
    affordable_defeat_ceiling_usd: float
    representative_threats: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class Query:
    """Validated user down-selection query."""

    mission_thread_id: str
    cost_threshold_usd: float
    flight_time_min: float
    distance_km: float
    aor_id: str
    posture_id: str = "attritable_first"
    max_cost_tier: str = "T4"
    asset_value_usd: float = 0.0


@dataclass(frozen=True)
class RetrievedDoc:
    """One retrieved knowledge base chunk with its relevance score."""

    doc_id: str
    title: str
    section: str
    text: str
    score: float


@dataclass(frozen=True)
class ScoredCandidate:
    """One equipment candidate with full score and economics breakdown."""

    equipment: Equipment
    classification: Classification
    exchange: ExchangeAnalysis
    total_score: float
    tier_multiplier: float
    hard_pass: bool
    score_breakdown: dict[str, float] = field(default_factory=dict)
    rationale: tuple[str, ...] = ()
    disqualifiers: tuple[str, ...] = ()
    watch_items: tuple[str, ...] = ()


@dataclass(frozen=True)
class SensitivityResult:
    """Rank stability of the effector list under deterministic perturbation."""

    scenarios: int
    top_pick_id: str
    top_pick_wins: int
    stable: bool
    rank_ranges: dict[str, tuple[int, int]]
    notes: str


@dataclass(frozen=True)
class ArchitectureLayer:
    """One layer of a proposed layered defense."""

    band: str
    band_range_km: tuple[float, float]
    system_name: str
    effective_pk: float
    magazine_cost_usd: float


@dataclass(frozen=True)
class LayeredArchitecture:
    """Layered defense proposal with combined cost and leakage."""

    layers: tuple[ArchitectureLayer, ...]
    sensor_name: str
    sensor_cost_usd: float
    total_magazine_cost_usd: float
    leakage_probability: float
    notes: str


@dataclass(frozen=True)
class Recommendation:
    """Complete recommendation package for one query."""

    query: Query
    posture: Posture
    aor: Aor
    thread: MissionThread
    relevant_groups: tuple[UasGroup, ...]
    ranked: tuple[ScoredCandidate, ...]
    enablers: tuple[ScoredCandidate, ...]
    baselines: tuple[ScoredCandidate, ...]
    rejected: tuple[ScoredCandidate, ...]
    retrieved_context: tuple[RetrievedDoc, ...]
    tier_distribution: dict[str, int]
    sensitivity: SensitivityResult | None
    architecture: LayeredArchitecture | None
    summary: str
