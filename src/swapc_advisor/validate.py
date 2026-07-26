"""Knowledge base validator.

Run as `swapc-validate`. Checks cross-references, enumerations, dates,
schema completeness, and — critically — rejects unknown fields. The
unknown-field check exists because schema drift was once observed landing
silently in the catalog; any field not in the allowlist now fails loudly.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Final

from .cli import default_data_dir
from .knowledge_base import load_knowledge_base
from .models import KnowledgeBaseError

DATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}$")
COST_CONFIDENCE_VALUES: Final[frozenset[str]] = frozenset(
    {"published", "estimated", "order_of_magnitude"}
)
EVIDENCE_VALUES: Final[frozenset[str]] = frozenset(
    {"combat_proven", "fielded", "demonstrated", "development", "concept"}
)
MATURITY_VALUES: Final[frozenset[str]] = frozenset({"startup", "scaleup", "prime"})
CATEGORY_VALUES: Final[frozenset[str]] = frozenset({"counter_uas", "uas_employment"})
WEIGHT_SUM_TOLERANCE: Final[float] = 0.001

ALLOWED_EQUIPMENT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "id",
        "name",
        "vendor",
        "vendor_maturity",
        "type",
        "category",
        "mission_threads",
        "target_groups",
        "swap_c",
        "flight_time_min",
        "effective_range_km",
        "single_shot_pk",
        "uses_per_unit",
        "units_per_month",
        "evidence_grade",
        "baseline_comparator",
        "environment_tags",
        "gps_denied_capable",
        "ew_resilient",
        "cost_confidence",
        "as_of",
        "source_note",
        "notes",
    }
)
ALLOWED_SWAP_FIELDS: Final[frozenset[str]] = frozenset(
    {"weight_lb", "size", "power_w", "unit_cost_usd"}
)


def _check_unknown_fields(entry: dict[str, Any]) -> list[str]:
    """Reject any field not in the allowlist. Silent schema drift is a defect."""
    errors: list[str] = []
    name: str = str(entry.get("id", "<no id>"))
    for key in entry:
        if key not in ALLOWED_EQUIPMENT_FIELDS:
            errors.append(f"{name}: unknown field '{key}' (schema drift or tampering)")
    swap: dict[str, Any] = entry.get("swap_c", {})
    for key in swap:
        if key not in ALLOWED_SWAP_FIELDS:
            errors.append(f"{name}: unknown swap_c field '{key}'")
    return errors


def _check_entry_values(entry: dict[str, Any]) -> list[str]:
    """Enumerations, dates, and Pk consistency for one equipment entry."""
    errors: list[str] = []
    name: str = str(entry.get("id", "<no id>"))
    if entry.get("cost_confidence") not in COST_CONFIDENCE_VALUES:
        errors.append(f"{name}: invalid cost_confidence '{entry.get('cost_confidence')}'")
    if entry.get("evidence_grade") not in EVIDENCE_VALUES:
        errors.append(f"{name}: invalid evidence_grade '{entry.get('evidence_grade')}'")
    if entry.get("vendor_maturity") not in MATURITY_VALUES:
        errors.append(f"{name}: invalid vendor_maturity '{entry.get('vendor_maturity')}'")
    if entry.get("category") not in CATEGORY_VALUES:
        errors.append(f"{name}: invalid category '{entry.get('category')}'")
    if not DATE_PATTERN.match(str(entry.get("as_of", ""))):
        errors.append(f"{name}: as_of '{entry.get('as_of')}' is not YYYY-MM")
    groups: set[int] = {int(g) for g in entry.get("target_groups", [])}
    for group_key in entry.get("single_shot_pk", {}):
        if int(group_key) not in groups:
            errors.append(f"{name}: Pk key group {group_key} not in target_groups")
    return errors


def _check_cross_references(data_dir: Path) -> list[str]:
    """Every mission thread reference must resolve to a defined thread."""
    errors: list[str] = []
    threads_doc: dict[str, Any] = json.loads(
        (data_dir / "mission_threads.json").read_text(encoding="utf-8")
    )
    valid_threads: set[str] = {t["id"] for t in threads_doc["mission_threads"]}
    equip_doc: dict[str, Any] = json.loads(
        (data_dir / "equipment.json").read_text(encoding="utf-8")
    )
    seen_ids: set[str] = set()
    for entry in equip_doc["equipment"]:
        name: str = str(entry.get("id", "<no id>"))
        if name in seen_ids:
            errors.append(f"duplicate equipment id: {name}")
        seen_ids.add(name)
        for thread_id in entry.get("mission_threads", []):
            if thread_id not in valid_threads:
                errors.append(f"{name}: unknown mission thread '{thread_id}'")
        errors.extend(_check_unknown_fields(entry))
        errors.extend(_check_entry_values(entry))
    return errors


def validate_data(data_dir: Path) -> list[str]:
    """Full validation pass. Returns a list of error strings; empty is clean."""
    errors: list[str] = []
    try:
        kb = load_knowledge_base(data_dir)
    except KnowledgeBaseError as exc:
        return [f"load failed: {exc}"]
    errors.extend(_check_cross_references(data_dir))
    tier_ceilings: list[float] = [t.max_unit_cost_usd for t in kb.taxonomy.cost_tiers]
    if tier_ceilings != sorted(tier_ceilings):
        errors.append("cost tier ceilings are not monotonically increasing")
    for posture in kb.taxonomy.postures:
        total: float = sum(posture.weights.values())
        if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
            errors.append(f"posture '{posture.posture_id}' weights sum to {total:.3f}, not 1.0")
    return errors


def main() -> int:
    """Console entry point: validate and report."""
    data_dir: Path = default_data_dir()
    if len(sys.argv) > 1:
        data_dir = Path(sys.argv[1])
    errors: list[str] = validate_data(data_dir)
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        print(f"\n{len(errors)} error(s) in {data_dir}")
        return 1
    print(f"OK knowledge base at {data_dir} is internally consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
