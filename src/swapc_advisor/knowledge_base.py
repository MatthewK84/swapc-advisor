"""Knowledge base loader and chunked corpus builder.

The corpus is chunked by section rather than one blob per entity. A query
about cost economics should retrieve the cost chunk, not an entire
equipment record whose relevant sentence is diluted by twenty others.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .models import (
    Aor,
    CostTier,
    Equipment,
    KnowledgeBaseError,
    MissionThread,
    Posture,
    SwapC,
    SwapTier,
    Taxonomy,
    UasGroup,
)

REQUIRED_FILES: Final[tuple[str, ...]] = (
    "aors.json",
    "uas_classes.json",
    "mission_threads.json",
    "equipment.json",
    "swapc_tiers.json",
)


@dataclass(frozen=True)
class Chunk:
    """One retrievable passage tagged with its source entity and section."""

    doc_id: str
    title: str
    section: str
    text: str


@dataclass(frozen=True)
class KnowledgeBase:
    """Immutable container for all loaded reference data."""

    aors: tuple[Aor, ...]
    uas_groups: tuple[UasGroup, ...]
    mission_threads: tuple[MissionThread, ...]
    equipment: tuple[Equipment, ...]
    taxonomy: Taxonomy
    disclaimer: str
    as_of: str

    def find_aor(self, aor_id: str) -> Aor | None:
        """Return the AOR matching the given id, case-insensitive."""
        wanted: str = aor_id.strip().upper()
        for aor in self.aors:
            if aor.aor_id.upper() == wanted:
                return aor
        return None

    def find_thread(self, thread_id: str) -> MissionThread | None:
        """Return the mission thread matching the given id."""
        wanted: str = thread_id.strip().lower()
        for thread in self.mission_threads:
            if thread.thread_id == wanted:
                return thread
        return None

    def groups_by_number(self, numbers: tuple[int, ...]) -> tuple[UasGroup, ...]:
        """Return UAS groups whose number appears in the given tuple."""
        return tuple(g for g in self.uas_groups if g.group in numbers)


def _read_json(path: Path) -> dict[str, Any]:
    """Read and parse one JSON file, raising KnowledgeBaseError on failure."""
    try:
        raw: str = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise KnowledgeBaseError(f"Cannot read {path}") from exc
    try:
        parsed: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise KnowledgeBaseError(f"Malformed JSON in {path}") from exc
    return parsed


def _parse_aor(entry: dict[str, Any]) -> Aor:
    """Build one Aor model from its JSON entry."""
    return Aor(
        aor_id=str(entry["id"]),
        name=str(entry["name"]),
        region=str(entry["region"]),
        environment_tags=tuple(entry["environment_tags"]),
        dominant_threat_groups=tuple(entry["dominant_threat_groups"]),
        ew_environment=str(entry["ew_environment"]),
        gps_environment=str(entry["gps_environment"]),
        median_threat_cost_usd=float(entry["median_threat_cost_usd"]),
        monthly_engagement_estimate=int(entry["monthly_engagement_estimate"]),
        resupply_difficulty=str(entry["resupply_difficulty"]),
        attritability_driver=str(entry["attritability_driver"]),
        threat_profile=str(entry["threat_profile"]),
        operating_notes=str(entry["operating_notes"]),
        exchange_context=str(entry["exchange_context"]),
    )


def _parse_group(entry: dict[str, Any]) -> UasGroup:
    """Build one UasGroup model from its JSON entry."""
    return UasGroup(
        group=int(entry["group"]),
        name=str(entry["name"]),
        max_weight_lb=float(entry["max_weight_lb"]),
        operating_altitude_ft=float(entry["operating_altitude_ft_agl"]),
        max_speed_kt=float(entry["max_speed_kt"]),
        endurance_min=(
            float(entry["typical_endurance_min"][0]),
            float(entry["typical_endurance_min"][1]),
        ),
        range_km=(
            float(entry["typical_range_km"][0]),
            float(entry["typical_range_km"][1]),
        ),
        unit_cost_usd=(
            float(entry["estimated_unit_cost_usd"][0]),
            float(entry["estimated_unit_cost_usd"][1]),
        ),
        median_threat_cost_usd=float(entry["median_threat_cost_usd"]),
        affordable_defeat_ceiling_usd=float(entry["affordable_defeat_ceiling_usd"]),
        representative_threats=tuple(entry["representative_threats"]),
        notes=str(entry["notes"]),
    )


def _parse_thread(entry: dict[str, Any]) -> MissionThread:
    """Build one MissionThread model from its JSON entry."""
    range_pair = entry["typical_engagement_range_km"]
    return MissionThread(
        thread_id=str(entry["id"]),
        name=str(entry["name"]),
        category=str(entry["category"]),
        target_groups=tuple(entry["target_groups"]),
        typical_salvo_size=int(entry["typical_salvo_size"]),
        exchange_ratio_target=float(entry["exchange_ratio_target"]),
        attritability_priority=str(entry["attritability_priority"]),
        description=str(entry["description"]),
        key_requirements=tuple(entry["key_requirements"]),
        engagement_range_km=(float(range_pair[0]), float(range_pair[1])),
    )


def _parse_equipment(entry: dict[str, Any]) -> Equipment:
    """Build one Equipment model from its JSON entry."""
    swap_raw: dict[str, Any] = entry["swap_c"]
    swap: SwapC = SwapC(
        weight_lb=float(swap_raw["weight_lb"]),
        size=str(swap_raw["size"]),
        power_w=float(swap_raw["power_w"]),
        unit_cost_usd=float(swap_raw["unit_cost_usd"]),
    )
    return Equipment(
        equipment_id=str(entry["id"]),
        name=str(entry["name"]),
        vendor=str(entry["vendor"]),
        vendor_maturity=str(entry["vendor_maturity"]),
        system_type=str(entry["type"]),
        category=str(entry["category"]),
        mission_threads=tuple(entry["mission_threads"]),
        target_groups=tuple(entry["target_groups"]),
        swap_c=swap,
        flight_time_min=float(entry["flight_time_min"]),
        effective_range_km=float(entry["effective_range_km"]),
        single_shot_pk=float(entry["single_shot_pk"]),
        uses_per_unit=int(entry["uses_per_unit"]),
        units_per_month=int(entry["units_per_month"]),
        evidence_grade=str(entry["evidence_grade"]),
        baseline_comparator=bool(entry["baseline_comparator"]),
        environment_tags=tuple(entry["environment_tags"]),
        gps_denied_capable=bool(entry["gps_denied_capable"]),
        ew_resilient=bool(entry["ew_resilient"]),
        cost_confidence=str(entry["cost_confidence"]),
        as_of=str(entry["as_of"]),
        source_note=str(entry["source_note"]),
        notes=str(entry["notes"]),
    )


def _parse_taxonomy(doc: dict[str, Any]) -> Taxonomy:
    """Build the Taxonomy model from swapc_tiers.json."""
    cost_tiers = tuple(
        CostTier(
            tier=str(e["tier"]),
            name=str(e["name"]),
            max_unit_cost_usd=float(e["max_unit_cost_usd"]),
            posture=str(e["posture"]),
            acquisition_note=str(e["acquisition_note"]),
            attritability=float(e["attritability"]),
        )
        for e in doc["cost_tiers"]
    )
    swap_tiers = tuple(
        SwapTier(
            tier=str(e["tier"]),
            name=str(e["name"]),
            max_weight_lb=float(e["max_weight_lb"]),
            max_power_w=float(e["max_power_w"]),
            emplacement=str(e["emplacement"]),
            logistics_note=str(e["logistics_note"]),
        )
        for e in doc["swap_tiers"]
    )
    postures = tuple(
        Posture(
            posture_id=str(e["id"]),
            name=str(e["name"]),
            intent=str(e["intent"]),
            weights={k: float(v) for k, v in e["weights"].items()},
            tier_multipliers={k: float(v) for k, v in e["tier_multipliers"].items()},
        )
        for e in doc["postures"]
    )
    evidence = {str(e["grade"]): float(e["confidence"]) for e in doc["evidence_grades"]}
    return Taxonomy(
        cost_tiers=cost_tiers,
        swap_tiers=swap_tiers,
        evidence_confidence=evidence,
        postures=postures,
    )


def load_knowledge_base(data_dir: Path) -> KnowledgeBase:
    """Load all reference data from the given directory."""
    for name in REQUIRED_FILES:
        if not (data_dir / name).is_file():
            raise KnowledgeBaseError(f"Missing required data file: {data_dir / name}")
    aor_doc: dict[str, Any] = _read_json(data_dir / "aors.json")
    group_doc: dict[str, Any] = _read_json(data_dir / "uas_classes.json")
    thread_doc: dict[str, Any] = _read_json(data_dir / "mission_threads.json")
    equip_doc: dict[str, Any] = _read_json(data_dir / "equipment.json")
    tier_doc: dict[str, Any] = _read_json(data_dir / "swapc_tiers.json")
    try:
        aors = tuple(_parse_aor(e) for e in aor_doc["aors"])
        groups = tuple(_parse_group(e) for e in group_doc["uas_groups"])
        threads = tuple(_parse_thread(e) for e in thread_doc["mission_threads"])
        equipment = tuple(_parse_equipment(e) for e in equip_doc["equipment"])
        taxonomy = _parse_taxonomy(tier_doc)
    except (KeyError, TypeError, ValueError) as exc:
        raise KnowledgeBaseError(f"Schema error in knowledge base: {exc}") from exc
    return KnowledgeBase(
        aors=aors,
        uas_groups=groups,
        mission_threads=threads,
        equipment=equipment,
        taxonomy=taxonomy,
        disclaimer=str(equip_doc.get("disclaimer", "")),
        as_of=str(equip_doc.get("as_of", "unknown")),
    )


def _aor_chunks(aor: Aor) -> list[Chunk]:
    """Three chunks per AOR: threat, environment, and exchange economics."""
    return [
        Chunk(
            f"aor:{aor.aor_id}",
            aor.name,
            "threat",
            f"{aor.name} {aor.region}. {aor.threat_profile}",
        ),
        Chunk(
            f"aor:{aor.aor_id}",
            aor.name,
            "environment",
            f"{aor.name} EW {aor.ew_environment}, GPS {aor.gps_environment}. "
            f"Environment {' '.join(aor.environment_tags)}. Resupply "
            f"{aor.resupply_difficulty}. {aor.operating_notes}",
        ),
        Chunk(
            f"aor:{aor.aor_id}",
            aor.name,
            "economics",
            f"{aor.name} median threat cost ${aor.median_threat_cost_usd:,.0f}, "
            f"about {aor.monthly_engagement_estimate} engagements per month, "
            f"attritability {aor.attritability_driver}. {aor.exchange_context}",
        ),
    ]


def _equipment_chunks(item: Equipment) -> list[Chunk]:
    """Three chunks per system: profile, economics, and provenance limits."""
    return [
        Chunk(
            f"equip:{item.equipment_id}",
            item.name,
            "profile",
            f"{item.name} by {item.vendor}, {item.system_type}, "
            f"{item.vendor_maturity} vendor. Threads "
            f"{' '.join(item.mission_threads)}. Groups {item.target_groups}. "
            f"Weight {item.swap_c.weight_lb} lb, power {item.swap_c.power_w} W. "
            f"Flight {item.flight_time_min} min, range {item.effective_range_km} km. "
            f"{item.notes} Environment {' '.join(item.environment_tags)}.",
        ),
        Chunk(
            f"equip:{item.equipment_id}",
            item.name,
            "economics",
            f"{item.name} unit cost ${item.swap_c.unit_cost_usd:,.0f}, "
            f"single-shot Pk {item.single_shot_pk}, {item.uses_per_unit} uses per "
            f"unit, production {item.units_per_month} per month. Attritable "
            f"expendable low cost interceptor economics magazine depth.",
        ),
        Chunk(
            f"equip:{item.equipment_id}",
            item.name,
            "provenance",
            f"{item.name} evidence grade {item.evidence_grade}, cost confidence "
            f"{item.cost_confidence}, as of {item.as_of}. {item.source_note}",
        ),
    ]


def build_corpus(kb: KnowledgeBase) -> tuple[Chunk, ...]:
    """Render every KB entry as section-tagged retrievable chunks."""
    chunks: list[Chunk] = []
    for aor in kb.aors:
        chunks.extend(_aor_chunks(aor))
    for group in kb.uas_groups:
        chunks.append(
            Chunk(
                f"group:{group.group}",
                group.name,
                "threat",
                f"{group.name}. Max weight {group.max_weight_lb} lb, endurance "
                f"{group.endurance_min[0]}-{group.endurance_min[1]} min, range "
                f"{group.range_km[0]}-{group.range_km[1]} km. Median threat cost "
                f"${group.median_threat_cost_usd:,.0f}, affordable defeat ceiling "
                f"${group.affordable_defeat_ceiling_usd:,.0f}. Threats "
                f"{', '.join(group.representative_threats)}. {group.notes}",
            )
        )
    for thread in kb.mission_threads:
        chunks.append(
            Chunk(
                f"thread:{thread.thread_id}",
                thread.name,
                "mission",
                f"{thread.name}. Targets groups {thread.target_groups}. Salvo "
                f"{thread.typical_salvo_size}, exchange target "
                f"{thread.exchange_ratio_target}:1, attritability "
                f"{thread.attritability_priority}. {thread.description} "
                f"Requirements {' '.join(thread.key_requirements)}.",
            )
        )
    for item in kb.equipment:
        chunks.extend(_equipment_chunks(item))
    for tier in kb.taxonomy.cost_tiers:
        chunks.append(
            Chunk(
                f"tier:{tier.tier}",
                f"{tier.tier} {tier.name}",
                "taxonomy",
                f"{tier.tier} {tier.name} up to ${tier.max_unit_cost_usd:,.0f} per "
                f"unit. {tier.posture} {tier.acquisition_note}",
            )
        )
    return tuple(chunks)
