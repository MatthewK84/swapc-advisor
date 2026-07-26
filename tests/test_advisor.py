"""Unit and end-to-end tests for the SWaP-C advisor."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import json
import shutil

from swapc_advisor.cost_model import (
    analyze_exchange,
    cost_per_defeat,
    effective_pk,
    is_enabler,
    rounds_per_defeat,
)
from swapc_advisor.knowledge_base import (
    KnowledgeBase,
    build_corpus,
    load_knowledge_base,
)
from swapc_advisor.models import Equipment, Query, ValidationError
from swapc_advisor.recommender import recommend, validate_query
from swapc_advisor.report_pdf import write_pdf
from swapc_advisor.report_xlsx import write_xlsx
from swapc_advisor.retriever import HybridRetriever, expand_query, tokenize
from swapc_advisor.taxonomy import classify, tier_rank, within_ceiling
from swapc_advisor.validate import validate_data

DATA_DIR = Path(__file__).resolve().parents[1] / "src" / "swapc_advisor" / "data"


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base(DATA_DIR)


def _item(kb: KnowledgeBase, equipment_id: str) -> Equipment:
    for item in kb.equipment:
        if item.equipment_id == equipment_id:
            return item
    raise AssertionError(f"missing {equipment_id}")


# --- knowledge base ---


def test_kb_loads_all_entities(kb) -> None:
    assert len(kb.aors) == 6
    assert len(kb.uas_groups) == 5
    assert len(kb.mission_threads) == 8
    assert len(kb.equipment) >= 25
    assert len(kb.taxonomy.cost_tiers) == 5
    assert len(kb.taxonomy.postures) == 3


def test_catalog_skews_attritable(kb) -> None:
    """The rebuilt catalog must be majority T0-T2, not POR-heavy."""
    tiers = [classify(i, kb.taxonomy).cost_tier for i in kb.equipment]
    low = sum(1 for t in tiers if t in {"T0", "T1", "T2"})
    assert low / len(tiers) > 0.6


# --- taxonomy ---


def test_cost_tier_assignment(kb) -> None:
    assert classify(_item(kb, "neros_archer"), kb.taxonomy).cost_tier == "T0"
    assert classify(_item(kb, "merops_as3"), kb.taxonomy).cost_tier == "T1"
    assert classify(_item(kb, "marss_mr"), kb.taxonomy).cost_tier == "T2"
    assert classify(_item(kb, "fortem_f700"), kb.taxonomy).cost_tier == "T3"
    assert classify(_item(kb, "leonidas"), kb.taxonomy).cost_tier == "T4"


def test_swap_tier_assignment(kb) -> None:
    assert classify(_item(kb, "mydefence_wingman"), kb.taxonomy).swap_tier == "S0"
    assert classify(_item(kb, "merops_as3"), kb.taxonomy).swap_tier == "S1"
    assert classify(_item(kb, "leonidas"), kb.taxonomy).swap_tier == "S4"


def test_tier_ceiling_logic() -> None:
    assert tier_rank("T0") == 0 and tier_rank("T4") == 4
    assert within_ceiling("T1", "T2") is True
    assert within_ceiling("T3", "T1") is False


# --- cost model ---


def test_rounds_per_defeat_inverts_pk(kb) -> None:
    item = _item(kb, "general_cherry_bullet")
    thread = kb.find_thread("owa_interdiction")  # groups 2,3 -> worst pk 0.40
    assert thread is not None
    assert 2.4 < rounds_per_defeat(item, thread) < 2.6


def test_reusability_amortizes_cost(kb) -> None:
    """A recoverable interceptor must cost less per defeat than its sticker."""
    road = _item(kb, "roadrunner_m")  # $500K, 4 uses, Pk 0.85
    thread = kb.find_thread("owa_interdiction")
    assert thread is not None
    assert cost_per_defeat(road, thread) < road.swap_c.unit_cost_usd


def test_hpm_beats_sticker_price_on_exchange(kb) -> None:
    """Leonidas has the worst unit cost but must not have the worst economics."""
    thread = kb.find_thread("fixed_site_defense")
    assert thread is not None
    hpm = cost_per_defeat(_item(kb, "leonidas"), thread)
    coyote = cost_per_defeat(_item(kb, "coyote_blk2"), thread)
    assert hpm < coyote


def test_sensors_flagged_as_enablers(kb) -> None:
    assert is_enabler(_item(kb, "acoustic_mesh")) is True
    assert is_enabler(_item(kb, "merops_as3")) is False


def test_merops_exchange_is_favorable(kb) -> None:
    """Ground truth: ~$15K interceptor vs ~$40K Shahed must be favorable."""
    thread = kb.find_thread("owa_interdiction")
    aor = kb.find_aor("CENTCOM")
    ex = analyze_exchange(_item(kb, "merops_as3"), thread, aor, kb.uas_groups)
    assert ex.favorable is True
    assert ex.exchange_ratio > 1.5


def test_exquisite_interceptor_exchange_is_unfavorable(kb) -> None:
    """A $125K round against a $40K threat must fail the exchange test."""
    thread = kb.find_thread("owa_interdiction")
    aor = kb.find_aor("CENTCOM")
    ex = analyze_exchange(_item(kb, "coyote_blk2"), thread, aor, kb.uas_groups)
    assert ex.favorable is False


def test_magazine_and_replenishment_computed(kb) -> None:
    thread = kb.find_thread("owa_interdiction")  # salvo 20
    aor = kb.find_aor("EUCOM")
    ex = analyze_exchange(_item(kb, "tytan_metis"), thread, aor, kb.uas_groups)
    assert ex.magazine_rounds >= 20
    assert ex.magazine_cost_usd > 0
    assert ex.replenish_days > 0


# --- retrieval ---


def test_query_expansion_maps_operator_phrasing() -> None:
    expanded = expand_query(tokenize("cheap interceptor"))
    assert "attritable" in expanded
    assert "expendable" in expanded


def test_retriever_finds_attritable_docs_from_cheap_query(kb) -> None:
    r = HybridRetriever(build_corpus(kb))
    hits = r.search("cheapest way to stop Shahed swarms", top_k=8)
    assert hits
    blob = " ".join(h.text.lower() for h in hits)
    assert "attritable" in blob or "shahed" in blob


def test_mmr_diversifies_entities(kb) -> None:
    """Top results must not all come from a single catalog entry."""
    r = HybridRetriever(build_corpus(kb))
    hits = r.search("attritable low cost interceptor economics", top_k=8)
    assert len({h.doc_id for h in hits}) >= 4


def test_section_tags_present(kb) -> None:
    r = HybridRetriever(build_corpus(kb))
    hits = r.search("cost exchange economics magazine", top_k=8)
    assert any(h.section == "economics" for h in hits)


# --- recommender ---


def test_attritable_posture_beats_por(kb) -> None:
    """Under the default posture, the top pick must not be a POR baseline."""
    q = Query("owa_interdiction", 600000.0, 0.0, 5.0, "CENTCOM")
    rec = recommend(kb, q)
    assert rec.ranked
    assert rec.ranked[0].equipment.baseline_comparator is False
    assert rec.ranked[0].classification.cost_tier in {"T0", "T1", "T2"}


def test_por_excluded_from_ranked_but_kept_as_baseline(kb) -> None:
    q = Query("owa_interdiction", 30000000.0, 0.0, 0.0, "CENTCOM")
    rec = recommend(kb, q)
    assert all(not c.equipment.baseline_comparator for c in rec.ranked)
    assert any(c.equipment.baseline_comparator for c in rec.baselines)


def test_capability_first_posture_shifts_ranking(kb) -> None:
    """Changing posture must change the score ordering or values."""
    base = Query("owa_interdiction", 600000.0, 0.0, 5.0, "CENTCOM")
    cap = Query("owa_interdiction", 600000.0, 0.0, 5.0, "CENTCOM", "capability_first")
    a = recommend(kb, base).ranked
    b = recommend(kb, cap).ranked
    assert [c.total_score for c in a] != [c.total_score for c in b]


def test_tier_ceiling_gate_excludes_higher_tiers(kb) -> None:
    q = Query("fixed_site_defense", 30000000.0, 0.0, 0.0, "CENTCOM", "attritable_first", "T1")
    rec = recommend(kb, q)
    for cand in rec.ranked:
        assert cand.classification.cost_tier in {"T0", "T1"}


def test_hard_gates_enforce_cost(kb) -> None:
    q = Query("fixed_site_defense", 10000.0, 0.0, 0.0, "CENTCOM")
    rec = recommend(kb, q)
    for cand in rec.ranked:
        assert cand.equipment.swap_c.unit_cost_usd <= 10000.0


def test_hard_gates_enforce_flight(kb) -> None:
    q = Query("isr_recon", 2000000.0, 200.0, 100.0, "INDOPACOM")
    rec = recommend(kb, q)
    for cand in rec.ranked:
        if cand.equipment.flight_time_min > 0:
            assert cand.equipment.flight_time_min >= 200.0
            assert cand.equipment.effective_range_km >= 100.0


def test_ranked_sorted_descending(kb) -> None:
    q = Query("fixed_site_defense", 30000000.0, 0.0, 0.0, "CENTCOM")
    rec = recommend(kb, q)
    scores = [c.total_score for c in rec.ranked]
    assert scores == sorted(scores, reverse=True)


def test_watch_items_flag_unverified_data(kb) -> None:
    """Development-grade systems must carry an explicit warning."""
    q = Query("fixed_site_defense", 30000000.0, 0.0, 0.0, "CENTCOM")
    rec = recommend(kb, q)
    bandit = [c for c in rec.ranked if c.equipment.equipment_id == "neros_bandit"]
    assert bandit
    assert any("unverified" in w.lower() for w in bandit[0].watch_items)


def test_tier_distribution_reported(kb) -> None:
    q = Query("fixed_site_defense", 30000000.0, 0.0, 0.0, "CENTCOM")
    rec = recommend(kb, q)
    assert sum(rec.tier_distribution.values()) == len(rec.ranked)


# --- validation ---


def test_invalid_aor_raises(kb) -> None:
    with pytest.raises(ValidationError):
        validate_query(kb, Query("isr_recon", 100000.0, 30.0, 5.0, "SPACECOM"))


def test_invalid_thread_raises(kb) -> None:
    with pytest.raises(ValidationError):
        validate_query(kb, Query("underwater_ops", 100000.0, 30.0, 5.0, "CENTCOM"))


def test_invalid_posture_raises(kb) -> None:
    with pytest.raises(ValidationError):
        validate_query(kb, Query("isr_recon", 1000.0, 5.0, 5.0, "CENTCOM", "yolo"))


def test_negative_cost_raises(kb) -> None:
    with pytest.raises(ValidationError):
        validate_query(kb, Query("isr_recon", -1.0, 30.0, 5.0, "CENTCOM"))


def test_empty_result_produces_actionable_bluf(kb) -> None:
    q = Query("isr_recon", 500.0, 9999.0, 9999.0, "CENTCOM")
    rec = recommend(kb, q)
    assert not rec.ranked
    assert "No cataloged system" in rec.summary


# --- effector / enabler separation ---


def test_enablers_separated_from_effectors(kb) -> None:
    """Detection-only systems must not appear in the effector ranking."""
    q = Query("owa_interdiction", 600000.0, 0.0, 5.0, "CENTCOM")
    rec = recommend(kb, q)
    assert all(not is_enabler(c.equipment) for c in rec.ranked)
    assert any(is_enabler(c.equipment) for c in rec.enablers)


def test_bluf_recommends_sensor_pairing(kb) -> None:
    q = Query("owa_interdiction", 600000.0, 0.0, 5.0, "CENTCOM")
    rec = recommend(kb, q)
    assert "Pair with" in rec.summary


# --- v2.1: per-group Pk, asset value, sensitivity, architecture, validation ---


def test_effective_pk_uses_worst_relevant_group(kb) -> None:
    """OWA interdiction engages Groups 2-3; Merops must plan on its G3 Pk."""
    merops = _item(kb, "merops_as3")  # {1:0.70, 2:0.65, 3:0.60}
    owa = kb.find_thread("owa_interdiction")
    maneuver = kb.find_thread("maneuver_force_protection")
    assert owa is not None and maneuver is not None
    assert effective_pk(merops, owa) == 0.60
    assert effective_pk(merops, maneuver) == 0.65


def test_asset_value_raises_exchange_ratio(kb) -> None:
    """Defending a $40M asset must justify effectors a bare threat cannot."""
    thread = kb.find_thread("critical_infrastructure")
    aor = kb.find_aor("NORTHCOM")
    assert thread is not None and aor is not None
    fortem = _item(kb, "fortem_f700")
    bare = analyze_exchange(fortem, thread, aor, kb.uas_groups)
    defended = analyze_exchange(fortem, thread, aor, kb.uas_groups, asset_value_usd=40_000_000.0)
    assert defended.exchange_ratio > bare.exchange_ratio
    assert defended.favorable


def test_sensitivity_runs_and_is_deterministic(kb) -> None:
    q = Query("owa_interdiction", 600000.0, 0.0, 5.0, "CENTCOM")
    a = recommend(kb, q)
    b = recommend(kb, q)
    assert a.sensitivity is not None and b.sensitivity is not None
    assert a.sensitivity.scenarios == 9
    assert a.sensitivity.top_pick_wins == b.sensitivity.top_pick_wins
    assert a.sensitivity.rank_ranges == b.sensitivity.rank_ranges


def test_sensitivity_rank_ranges_cover_all_effectors(kb) -> None:
    q = Query("owa_interdiction", 600000.0, 0.0, 5.0, "CENTCOM")
    rec = recommend(kb, q)
    assert rec.sensitivity is not None
    for cand in rec.ranked:
        low, high = rec.sensitivity.rank_ranges[cand.equipment.equipment_id]
        assert 1 <= low <= high


def test_architecture_builds_layers(kb) -> None:
    q = Query("fixed_site_defense", 30000000.0, 0.0, 0.0, "CENTCOM")
    rec = recommend(kb, q)
    assert rec.architecture is not None
    assert 1 <= len(rec.architecture.layers) <= 3
    assert 0.0 <= rec.architecture.leakage_probability < 1.0
    assert rec.architecture.total_magazine_cost_usd > 0


def test_validator_clean_on_shipped_data() -> None:
    assert validate_data(DATA_DIR) == []


def test_validator_rejects_unknown_field(tmp_path) -> None:
    """The guard born from observed schema drift: foreign fields must fail."""
    work = tmp_path / "data"
    shutil.copytree(DATA_DIR, work)
    doc = json.loads((work / "equipment.json").read_text())
    doc["equipment"][0]["pk_by_group"] = {"1": 0.5}
    (work / "equipment.json").write_text(json.dumps(doc))
    errors = validate_data(work)
    assert any("unknown field" in e for e in errors)


def test_validator_rejects_bad_thread_reference(tmp_path) -> None:
    work = tmp_path / "data"
    shutil.copytree(DATA_DIR, work)
    doc = json.loads((work / "equipment.json").read_text())
    doc["equipment"][0]["mission_threads"] = ["underwater_ops"]
    (work / "equipment.json").write_text(json.dumps(doc))
    errors = validate_data(work)
    assert any("unknown mission thread" in e for e in errors)


# --- report writers: end-to-end file generation ---


def test_reports_generate_end_to_end(kb, tmp_path) -> None:
    """Both writers must produce nonzero files for a real recommendation.

    Exists because a schema change once broke the Excel writer while every
    other test stayed green: nothing exercised the report layer.
    """
    q = Query("owa_interdiction", 600000.0, 5.0, 8.0, "CENTCOM")
    rec = recommend(kb, q)
    pdf = write_pdf(rec, tmp_path / "r.pdf", kb.disclaimer)
    xlsx = write_xlsx(rec, tmp_path / "r.xlsx", kb.disclaimer)
    assert pdf.stat().st_size > 5000
    assert xlsx.stat().st_size > 5000


def test_reports_generate_for_empty_result(kb, tmp_path) -> None:
    """Writers must not crash when nothing passes the gates."""
    q = Query("isr_recon", 500.0, 9999.0, 9999.0, "CENTCOM")
    rec = recommend(kb, q)
    assert not rec.ranked
    assert write_pdf(rec, tmp_path / "e.pdf", kb.disclaimer).stat().st_size > 0
    assert write_xlsx(rec, tmp_path / "e.xlsx", kb.disclaimer).stat().st_size > 0
