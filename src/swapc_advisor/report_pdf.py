"""PDF report generation with reportlab.

BLUF-first layout: summary, inputs, tier distribution, ranked candidates
with exchange economics, POR baseline delta, watch items, threat
reference, and retrieved RAG context.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, StyleSheet1, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import Recommendation, ReportError, ScoredCandidate

ACCENT: Final[colors.Color] = colors.HexColor("#1a3a5c")
LIGHT_ROW: Final[colors.Color] = colors.HexColor("#eef2f6")
WARN_BG: Final[colors.Color] = colors.HexColor("#fdf3e3")
MAX_RANKED: Final[int] = 6
OPEN_ENDED_KM: Final[float] = 999.0


def _styles() -> StyleSheet1:
    """Sample stylesheet extended with report-specific paragraph styles."""
    base: StyleSheet1 = getSampleStyleSheet()
    base.add(
        ParagraphStyle(
            "Bluf",
            parent=base["Normal"],
            fontSize=10.5,
            leading=14,
            backColor=colors.HexColor("#f4f0e6"),
            borderPadding=8,
        )
    )
    base.add(ParagraphStyle("Cell", parent=base["Normal"], fontSize=8, leading=10))
    base.add(
        ParagraphStyle(
            "Warn",
            parent=base["Normal"],
            fontSize=8.5,
            leading=11,
            backColor=WARN_BG,
            borderPadding=6,
        )
    )
    base.add(
        ParagraphStyle(
            "SectionHead",
            parent=base["Heading2"],
            textColor=ACCENT,
            spaceBefore=12,
            spaceAfter=5,
            fontSize=13,
        )
    )
    return base


def _grid_style() -> TableStyle:
    """Shared table style: header band, grid, alternating rows."""
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8c4d0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_ROW]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
    )


def _header_block(rec: Recommendation, styles: StyleSheet1) -> list[object]:
    """Title, timestamp, classification banner, and BLUF paragraph."""
    stamp: str = datetime.now(timezone.utc).strftime("%d %b %Y %H:%MZ")
    return [
        Paragraph("UNCLASSIFIED // OPEN-SOURCE ESTIMATES", styles["Cell"]),
        Spacer(1, 5),
        Paragraph("SWaP-C Down-Selection Report", styles["Title"]),
        Paragraph(
            f"{rec.thread.name} | {rec.aor.aor_id} | Posture: {rec.posture.name} "
            f"| Generated {stamp}",
            styles["Normal"],
        ),
        Spacer(1, 10),
        Paragraph(rec.summary, styles["Bluf"]),
        Spacer(1, 4),
    ]


def _inputs_table(rec: Recommendation, styles: StyleSheet1) -> Table:
    """Two-column table of the user's query inputs and derived context."""
    q = rec.query
    tiers: str = ", ".join(f"{k}: {v}" for k, v in sorted(rec.tier_distribution.items()))
    pairs: tuple[tuple[str, str], ...] = (
        ("Mission thread", rec.thread.name),
        ("AOR", f"{rec.aor.name} ({rec.aor.aor_id})"),
        ("Cost per unit threshold", f"${q.cost_threshold_usd:,.0f}"),
        ("Flight time requirement", f"{q.flight_time_min:.0f} min"),
        ("Distance requirement", f"{q.distance_km:.0f} km"),
        ("Scoring posture", f"{rec.posture.name} — {rec.posture.intent}"),
        ("Cost tier ceiling", q.max_cost_tier),
        ("Reference threat cost", f"${rec.aor.median_threat_cost_usd:,.0f}"),
        ("Exchange ratio target", f"{rec.thread.exchange_ratio_target:.0f}:1"),
        ("Assumed salvo size", f"{rec.thread.typical_salvo_size} threats"),
        ("Passing candidates by tier", tiers if tiers else "none"),
    )
    rows: list[list[Paragraph]] = [
        [Paragraph("<b>Input</b>", styles["Cell"]), Paragraph("<b>Value</b>", styles["Cell"])]
    ]
    for label, value in pairs:
        rows.append([Paragraph(label, styles["Cell"]), Paragraph(value, styles["Cell"])])
    table: Table = Table(rows, colWidths=[1.8 * inch, 5.4 * inch])
    table.setStyle(_grid_style())
    return table


def _candidate_rows(
    candidates: tuple[ScoredCandidate, ...], styles: StyleSheet1
) -> list[list[Paragraph]]:
    """Table rows for the ranked recommendation table."""
    headers: tuple[str, ...] = (
        "#",
        "System",
        "Tier",
        "Score",
        "Unit Cost",
        "Per Defeat",
        "Exch",
        "SWaP",
        "Prod/mo",
        "Evidence",
    )
    rows: list[list[Paragraph]] = [[Paragraph(f"<b>{h}</b>", styles["Cell"]) for h in headers]]
    for rank, cand in enumerate(candidates, start=1):
        e = cand.equipment
        per_defeat: str = (
            f"${cand.exchange.cost_per_defeat_usd:,.0f}"
            if cand.exchange.cost_per_defeat_usd > 0
            else "enabler"
        )
        ratio: str = (
            f"{cand.exchange.exchange_ratio:.1f}:1" if cand.exchange.exchange_ratio > 0 else "n/a"
        )
        rows.append(
            [
                Paragraph(str(rank), styles["Cell"]),
                Paragraph(f"<b>{e.name}</b><br/>{e.vendor}", styles["Cell"]),
                Paragraph(
                    f"{cand.classification.cost_tier}<br/>{cand.classification.swap_tier}",
                    styles["Cell"],
                ),
                Paragraph(f"{cand.total_score:.2f}", styles["Cell"]),
                Paragraph(f"${e.swap_c.unit_cost_usd:,.0f}", styles["Cell"]),
                Paragraph(per_defeat, styles["Cell"]),
                Paragraph(ratio, styles["Cell"]),
                Paragraph(
                    f"{e.swap_c.weight_lb:,.0f} lb<br/>{e.swap_c.power_w:,.0f} W", styles["Cell"]
                ),
                Paragraph(f"{e.units_per_month:,}", styles["Cell"]),
                Paragraph(e.evidence_grade.replace("_", " "), styles["Cell"]),
            ]
        )
    return rows


def _ranked_section(rec: Recommendation, styles: StyleSheet1) -> list[object]:
    """Ranked recommendations table plus per-candidate rationale."""
    story: list[object] = [Paragraph("Ranked Effectors (Attritable Set)", styles["SectionHead"])]
    if not rec.ranked:
        story.append(Paragraph("No system passed all hard gates. See BLUF.", styles["Normal"]))
        return story
    shown: tuple[ScoredCandidate, ...] = rec.ranked[:MAX_RANKED]
    widths: list[float] = [0.25, 1.15, 0.42, 0.42, 0.72, 0.72, 0.5, 0.7, 0.58, 0.74]
    table: Table = Table(_candidate_rows(shown, styles), colWidths=[w * inch for w in widths])
    table.setStyle(_grid_style())
    story.append(table)
    story.append(Spacer(1, 8))
    for rank, cand in enumerate(shown[:3], start=1):
        story.append(
            Paragraph(
                f"<b>{rank}. {cand.equipment.name}</b> — {' '.join(cand.rationale[:3])}",
                styles["Cell"],
            )
        )
        story.append(Spacer(1, 3))
    return story


def _enabler_section(rec: Recommendation, styles: StyleSheet1) -> list[object]:
    """Detection and cueing layer, listed separately from effectors."""
    if not rec.enablers:
        return []
    story: list[object] = [
        Paragraph("Detection and Cueing Layer (Enablers)", styles["SectionHead"]),
        Paragraph(
            "These are not substitutes for an effector and are ranked separately. "
            "Attritable interceptors are only employable with an external sensor "
            "picture, so the architecture needs at least one of these.",
            styles["Cell"],
        ),
        Spacer(1, 5),
    ]
    headers: tuple[str, ...] = ("System", "Tier", "Unit Cost", "Range", "SWaP", "Note")
    rows: list[list[Paragraph]] = [[Paragraph(f"<b>{h}</b>", styles["Cell"]) for h in headers]]
    for cand in rec.enablers:
        e = cand.equipment
        rows.append(
            [
                Paragraph(f"<b>{e.name}</b><br/>{e.vendor}", styles["Cell"]),
                Paragraph(
                    f"{cand.classification.cost_tier}/{cand.classification.swap_tier}",
                    styles["Cell"],
                ),
                Paragraph(f"${e.swap_c.unit_cost_usd:,.0f}", styles["Cell"]),
                Paragraph(f"{e.effective_range_km:.1f} km", styles["Cell"]),
                Paragraph(
                    f"{e.swap_c.weight_lb:,.0f} lb / {e.swap_c.power_w:,.0f} W", styles["Cell"]
                ),
                Paragraph(e.notes, styles["Cell"]),
            ]
        )
    widths: list[float] = [1.15, 0.5, 0.72, 0.55, 0.95, 3.33]
    table: Table = Table(rows, colWidths=[w * inch for w in widths])
    table.setStyle(_grid_style())
    story.append(table)
    return story


def _baseline_section(rec: Recommendation, styles: StyleSheet1) -> list[object]:
    """Program-of-record comparators with the exchange delta made explicit."""
    if not rec.baselines:
        return []
    story: list[object] = [
        Paragraph("Program-of-Record Baseline Comparison", styles["SectionHead"]),
        Paragraph(
            "These systems are excluded from the ranked set by design. They are "
            "shown so the cost-exchange delta of the attritable recommendation is "
            "explicit, and so any capability genuinely unique to them is visible.",
            styles["Cell"],
        ),
        Spacer(1, 5),
    ]
    headers: tuple[str, ...] = (
        "System",
        "Tier",
        "Unit Cost",
        "Per Defeat",
        "Exch",
        "Delta vs Top",
        "Note",
    )
    rows: list[list[Paragraph]] = [[Paragraph(f"<b>{h}</b>", styles["Cell"]) for h in headers]]
    top_cost: float = rec.ranked[0].exchange.cost_per_defeat_usd if rec.ranked else 0.0
    for cand in rec.baselines:
        delta: str = "n/a"
        if top_cost > 0 and cand.exchange.cost_per_defeat_usd > 0:
            delta = f"{cand.exchange.cost_per_defeat_usd / top_cost:.1f}x costlier"
        rows.append(
            [
                Paragraph(f"<b>{cand.equipment.name}</b>", styles["Cell"]),
                Paragraph(cand.classification.cost_tier, styles["Cell"]),
                Paragraph(f"${cand.equipment.swap_c.unit_cost_usd:,.0f}", styles["Cell"]),
                Paragraph(f"${cand.exchange.cost_per_defeat_usd:,.0f}", styles["Cell"]),
                Paragraph(f"{cand.exchange.exchange_ratio:.2f}:1", styles["Cell"]),
                Paragraph(delta, styles["Cell"]),
                Paragraph(cand.equipment.notes, styles["Cell"]),
            ]
        )
    widths: list[float] = [1.05, 0.35, 0.72, 0.7, 0.5, 0.78, 3.1]
    table: Table = Table(rows, colWidths=[w * inch for w in widths])
    table.setStyle(_grid_style())
    story.append(table)
    return story


def _magazine_section(rec: Recommendation, styles: StyleSheet1) -> list[object]:
    """Magazine cost and production replenishment for the top candidates."""
    if not rec.ranked:
        return []
    story: list[object] = [
        Paragraph("Magazine Depth and Replenishment", styles["SectionHead"]),
        Paragraph(
            f"Sized against a {rec.thread.typical_salvo_size}-threat salvo at "
            f"{rec.aor.monthly_engagement_estimate} estimated engagements per month "
            f"in {rec.aor.aor_id}.",
            styles["Cell"],
        ),
        Spacer(1, 5),
    ]
    headers: tuple[str, ...] = (
        "System",
        "Rounds/Defeat",
        "Magazine Rounds",
        "Magazine Cost",
        "Replenish (days)",
    )
    rows: list[list[Paragraph]] = [[Paragraph(f"<b>{h}</b>", styles["Cell"]) for h in headers]]
    for cand in rec.ranked[:MAX_RANKED]:
        ex = cand.exchange
        rounds: str = f"{ex.rounds_per_defeat:.2f}" if ex.rounds_per_defeat > 0 else "n/a"
        rows.append(
            [
                Paragraph(cand.equipment.name, styles["Cell"]),
                Paragraph(rounds, styles["Cell"]),
                Paragraph(f"{ex.magazine_rounds:,}", styles["Cell"]),
                Paragraph(f"${ex.magazine_cost_usd:,.0f}", styles["Cell"]),
                Paragraph(f"{ex.replenish_days:.1f}", styles["Cell"]),
            ]
        )
    table: Table = Table(
        rows, colWidths=[2.3 * inch, 1.0 * inch, 1.2 * inch, 1.4 * inch, 1.3 * inch]
    )
    table.setStyle(_grid_style())
    story.append(table)
    return story


def _sensitivity_section(rec: Recommendation, styles: StyleSheet1) -> list[object]:
    """Rank stability under cost and Pk perturbation."""
    if rec.sensitivity is None:
        return []
    sens = rec.sensitivity
    story: list[object] = [
        Paragraph("Sensitivity Analysis", styles["SectionHead"]),
        Paragraph(
            "Deterministic 3x3 grid: unit cost x0.5/x1.0/x1.5, Pk -0.15/0/+0.15. "
            "Rank ranges show each candidate's best and worst position across "
            "all nine scenarios.",
            styles["Cell"],
        ),
        Spacer(1, 4),
        Paragraph(sens.notes, styles["Warn"] if not sens.stable else styles["Cell"]),
        Spacer(1, 5),
    ]
    rows: list[list[Paragraph]] = [
        [Paragraph(f"<b>{h}</b>", styles["Cell"]) for h in ("System", "Rank Range", "Verdict")]
    ]
    for cand in rec.ranked:
        eq_id: str = cand.equipment.equipment_id
        low, high = sens.rank_ranges.get(eq_id, (0, 0))
        verdict: str = "Stable" if low == high else f"Varies {low}-{high}"
        rows.append(
            [
                Paragraph(cand.equipment.name, styles["Cell"]),
                Paragraph(f"{low}-{high}", styles["Cell"]),
                Paragraph(verdict, styles["Cell"]),
            ]
        )
    table: Table = Table(rows, colWidths=[3.0 * inch, 1.2 * inch, 3.0 * inch])
    table.setStyle(_grid_style())
    story.append(table)
    return story


def _architecture_section(rec: Recommendation, styles: StyleSheet1) -> list[object]:
    """Layered defense proposal with combined cost and leakage."""
    if rec.architecture is None:
        return []
    arch = rec.architecture
    story: list[object] = [
        Paragraph("Layered Architecture Proposal", styles["SectionHead"]),
        Paragraph(arch.notes, styles["Cell"]),
        Spacer(1, 5),
    ]
    rows: list[list[Paragraph]] = [
        [
            Paragraph(f"<b>{h}</b>", styles["Cell"])
            for h in ("Layer", "Band (km)", "System", "Effective Pk", "Magazine Cost")
        ]
    ]
    for layer in arch.layers:
        band: str = f"{layer.band_range_km[0]:.0f}-{layer.band_range_km[1]:.0f}"
        if layer.band_range_km[1] >= OPEN_ENDED_KM:
            band = f"{layer.band_range_km[0]:.0f}+"
        rows.append(
            [
                Paragraph(layer.band, styles["Cell"]),
                Paragraph(band, styles["Cell"]),
                Paragraph(layer.system_name, styles["Cell"]),
                Paragraph(f"{layer.effective_pk:.2f}", styles["Cell"]),
                Paragraph(f"${layer.magazine_cost_usd:,.0f}", styles["Cell"]),
            ]
        )
    rows.append(
        [
            Paragraph("<b>Sensor</b>", styles["Cell"]),
            Paragraph("-", styles["Cell"]),
            Paragraph(arch.sensor_name, styles["Cell"]),
            Paragraph("-", styles["Cell"]),
            Paragraph(f"${arch.sensor_cost_usd:,.0f}", styles["Cell"]),
        ]
    )
    table: Table = Table(
        rows, colWidths=[0.8 * inch, 0.9 * inch, 2.6 * inch, 1.0 * inch, 1.9 * inch]
    )
    table.setStyle(_grid_style())
    story.append(table)
    story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            f"<b>Total architecture magazine cost: "
            f"${arch.total_magazine_cost_usd:,.0f}. Leakage: "
            f"{arch.leakage_probability:.1%}.</b>",
            styles["Cell"],
        )
    )
    return story


def _watch_section(rec: Recommendation, styles: StyleSheet1) -> list[object]:
    """Risks and data-confidence caveats for the top candidates."""
    flagged: tuple[ScoredCandidate, ...] = tuple(
        c for c in rec.ranked[:MAX_RANKED] if c.watch_items
    )
    if not flagged:
        return []
    story: list[object] = [Paragraph("Watch Items", styles["SectionHead"])]
    for cand in flagged:
        bullets: str = "<br/>".join(f"- {w}" for w in cand.watch_items)
        story.append(Paragraph(f"<b>{cand.equipment.name}</b><br/>{bullets}", styles["Warn"]))
        story.append(Spacer(1, 4))
    return story


def _context_section(rec: Recommendation, styles: StyleSheet1) -> list[object]:
    """Threat reference and retrieved RAG context passages."""
    story: list[object] = [Paragraph("Threat Reference", styles["SectionHead"])]
    for group in rec.relevant_groups:
        story.append(
            Paragraph(
                f"<b>{group.name}:</b> {', '.join(group.representative_threats)}. "
                f"Median threat cost ${group.median_threat_cost_usd:,.0f}; affordable "
                f"defeat ceiling ${group.affordable_defeat_ceiling_usd:,.0f}. {group.notes}",
                styles["Cell"],
            )
        )
        story.append(Spacer(1, 3))
    story.append(Paragraph("Retrieved Knowledge Base Context", styles["SectionHead"]))
    for doc in rec.retrieved_context:
        story.append(
            Paragraph(
                f"<b>{doc.title}</b> [{doc.section}] (relevance {doc.score:.1f}): {doc.text}",
                styles["Cell"],
            )
        )
        story.append(Spacer(1, 3))
    return story


def write_pdf(rec: Recommendation, out_path: Path, disclaimer: str) -> Path:
    """Render the full recommendation report to a PDF file."""
    styles: StyleSheet1 = _styles()
    story: list[object] = _header_block(rec, styles)
    story.append(_inputs_table(rec, styles))
    story.extend(_ranked_section(rec, styles))
    story.extend(_enabler_section(rec, styles))
    story.extend(_baseline_section(rec, styles))
    story.extend(_magazine_section(rec, styles))
    story.extend(_sensitivity_section(rec, styles))
    story.extend(_architecture_section(rec, styles))
    story.extend(_watch_section(rec, styles))
    story.extend(_context_section(rec, styles))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"<i>{disclaimer}</i>", styles["Cell"]))
    doc: SimpleDocTemplate = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title="SWaP-C Down-Selection Report",
    )
    try:
        doc.build(story)
    except (OSError, ValueError) as exc:
        raise ReportError(f"PDF generation failed: {exc}") from exc
    return out_path
