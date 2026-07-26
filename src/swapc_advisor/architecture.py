"""Layered defense architecture.

Real C-UAS is layered: a single effector recommendation understates both
the cost and the achievable defeat probability. This module assembles the
best passing effector per range band, pairs the best enabler, and reports
combined magazine cost and leakage (the probability a threat survives
every layer it transits).
"""

from __future__ import annotations

from typing import Final

from .cost_model import effective_pk, is_enabler
from .models import (
    ArchitectureLayer,
    LayeredArchitecture,
    MissionThread,
    ScoredCandidate,
)

OPEN_ENDED_KM: Final[float] = 999.0
BANDS: Final[tuple[tuple[str, float, float], ...]] = (
    ("Outer", 10.0, OPEN_ENDED_KM),
    ("Mid", 3.0, 10.0),
    ("Terminal", 0.0, 3.0),
)


def _band_pick(
    candidates: tuple[ScoredCandidate, ...], low_km: float, high_km: float
) -> ScoredCandidate | None:
    """Best-scoring effector whose reach covers the band's outer edge."""
    for cand in candidates:
        reach: float = cand.equipment.effective_range_km
        if low_km < reach and (reach >= high_km or high_km >= OPEN_ENDED_KM):
            return cand
    for cand in candidates:
        if cand.equipment.effective_range_km > low_km:
            return cand
    return None


def _leakage(layers: tuple[ArchitectureLayer, ...]) -> float:
    """Probability a threat survives one engagement per transited layer."""
    survive: float = 1.0
    for layer in layers:
        survive *= 1.0 - layer.effective_pk
    return survive


def _architecture_note(
    layers: tuple[ArchitectureLayer, ...], leakage: float, thread: MissionThread
) -> str:
    """Plain-language reading of the layered result."""
    count: int = len(layers)
    per_salvo: float = leakage * thread.typical_salvo_size
    return (
        f"{count}-layer architecture assuming one engagement per layer. "
        f"Leakage {leakage:.1%}: of a {thread.typical_salvo_size}-threat "
        f"salvo, expect about {per_salvo:.1f} leakers reaching the terminal "
        f"point, before reattack. Deepen magazines or add a layer to drive "
        f"this down."
    )


def build_architecture(
    ranked: tuple[ScoredCandidate, ...],
    enablers: tuple[ScoredCandidate, ...],
    thread: MissionThread,
) -> LayeredArchitecture | None:
    """Assemble a layered proposal from the passing candidate sets."""
    effectors: tuple[ScoredCandidate, ...] = tuple(c for c in ranked if not is_enabler(c.equipment))
    if not effectors:
        return None
    layers: list[ArchitectureLayer] = []
    used: set[str] = set()
    for band_name, low_km, high_km in BANDS:
        pool: tuple[ScoredCandidate, ...] = tuple(
            c for c in effectors if c.equipment.equipment_id not in used
        )
        pick: ScoredCandidate | None = _band_pick(pool, low_km, high_km)
        if pick is None:
            pick = _band_pick(effectors, low_km, high_km)
        if pick is None:
            continue
        used.add(pick.equipment.equipment_id)
        layers.append(
            ArchitectureLayer(
                band=band_name,
                band_range_km=(low_km, high_km),
                system_name=pick.equipment.name,
                effective_pk=round(effective_pk(pick.equipment, thread), 3),
                magazine_cost_usd=pick.exchange.magazine_cost_usd,
            )
        )
    if not layers:
        return None
    layer_tuple: tuple[ArchitectureLayer, ...] = tuple(layers)
    sensor_name: str = enablers[0].equipment.name if enablers else "None cataloged"
    sensor_cost: float = enablers[0].equipment.swap_c.unit_cost_usd if enablers else 0.0
    leakage: float = _leakage(layer_tuple)
    return LayeredArchitecture(
        layers=layer_tuple,
        sensor_name=sensor_name,
        sensor_cost_usd=sensor_cost,
        total_magazine_cost_usd=round(
            sum(layer.magazine_cost_usd for layer in layer_tuple) + sensor_cost, 2
        ),
        leakage_probability=round(leakage, 4),
        notes=_architecture_note(layer_tuple, leakage, thread),
    )
