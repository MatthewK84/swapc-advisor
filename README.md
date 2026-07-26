# SWaP-C Down-Selection Advisor (v2 — attritable-first)

BLUF: Offline RAG-backed down-selection tool for UAS and C-sUAS technology, retuned to surface and classify ultra-low SWaP-C platforms instead of programs of record. You supply four inputs. The tool returns a tier-classified, cost-exchange-justified recommendation as PDF and Excel.

## What changed from v1

v1 ranked on unit cost, mission fit, and a **fielding-maturity bonus**. That bonus systematically rewarded programs of record: the same CENTCOM OWA query returned a $500K Roadrunner-M. v2 returns a $3K round at **23.4x lower cost per defeat**, with the POR shown only as the baseline it beats.

Seven changes produced that:

1. **Cost-exchange model replaces unit-cost ranking.** Unit cost misranks effectors. A recoverable interceptor amortizes across sorties, a jammer across thousands of engagements, and a low-Pk round needs several attempts per defeat. `cost_model.py` reduces all of it to cost per defeat and its ratio against threat cost.
2. **Two-axis tier classification.** Every system is auto-assigned a cost tier (T0 Consumable → T4 Exquisite) and a SWaP tier (S0 Pocket → S4 Fixed Site) from its own figures, so labels cannot drift from the catalog.
3. **Maturity bonus inverted into a tier penalty.** Under the default posture T3 scores ×0.85 and T4 ×0.65. Evidence grade survives as a modest 10% discipline term so vaporware cannot win.
4. **PORs moved to a baseline set.** They are excluded from the ranked list by design and reported separately with an explicit cost-per-defeat delta.
5. **Production rate is now a scored factor.** A magazine you cannot replenish is not a magazine. Reports include magazine cost and replenishment days at stated production rate.
6. **Effectors separated from enablers.** Sensors are not substitutes for interceptors. They rank separately, and the BLUF recommends a pairing, because attritable effectors need an external sensor picture to be employable at all.
7. **RAG rebuilt** (see below).

## The four inputs

| Flag | Meaning |
|---|---|
| `--mission-thread` | One of 8 threads (5 C-sUAS, 3 UAS employment) |
| `--cost-threshold` | Maximum acceptable cost per unit, USD |
| `--flight-time` | Required flight time, minutes (0 for ground-based) |
| `--distance` | Required flight distance or engagement range, km |
| `--aor` | CENTCOM, EUCOM, INDOPACOM, AFRICOM, SOUTHCOM, NORTHCOM |

Two optional flags control aggressiveness:

| Flag | Default | Effect |
|---|---|---|
| `--posture` | `attritable_first` | Also `balanced`, `capability_first`. Shifts all seven scoring weights and tier penalties. |
| `--max-cost-tier` | `T4` | Hard ceiling. `--max-cost-tier T1` excludes anything above attritable. |

## Install and run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

swapc-advisor \
  --mission-thread owa_interdiction \
  --cost-threshold 600000 \
  --flight-time 5 \
  --distance 8 \
  --aor CENTCOM \
  --out-dir output
```

Add `--data-dir /path/to/data` to point at an alternate knowledge base.

Mission threads: `fixed_site_defense`, `maneuver_force_protection`, `critical_infrastructure`, `maritime_port_defense`, `owa_interdiction`, `isr_recon`, `precision_strike`, `logistics_resupply`.

## The RAG rebuild

The v1 retriever was plain BM25 over one document per entity. Three specific failures drove the rewrite:

1. **Query expansion.** Operators write "cheap interceptor"; the catalog says "attritable" and "expendable". A 30-entry domain lexicon bridges operator phrasing to catalog wording, so `cheap` also retrieves attritable, expendable, low-cost, affordable.
2. **Section chunking and boosting.** v1 returned an entire equipment record whose one relevant sentence was diluted by twenty others. v2 emits three chunks per system (profile, economics, provenance) and three per AOR (threat, environment, economics), then boosts chunks whose section matches the query's inferred intent by 1.35x.
3. **MMR diversification.** v1's top-8 returned three chunks of the same system and crowded out the AOR and threat context the report needs. v2 applies iterative maximal-marginal-relevance selection (λ=0.7) penalizing repeat entities.

Still dependency-free, deterministic, and offline, so it runs identically on air-gapped NIPR and SIPR hosts.

## Scoring

Seven factors, weighted by posture. Default `attritable_first`:

| Factor | Weight | Notes |
|---|---|---|
| Cost exchange | 28% | Log-normalized ratio against the thread's exchange target |
| SWaP efficiency | 18% | Log-scaled weight (60%) and power (40%) |
| Mission thread fit | 15% | Listed match 1.0, same category 0.4 |
| AOR fit | 12% | Environment overlap + EW + GNSS suitability |
| Threat group coverage | 10% | — |
| Production rate | 10% | Log-scaled against 3,000/month |
| Evidence grade | 10% | combat_proven 1.0 → concept 0.1 |

Then multiplied by the tier penalty. Hard gates (cost, tier ceiling, flight time, distance) run before scoring; ground-based effectors are flight-exempt.

## Architecture

```
src/swapc_advisor/
  data/                Knowledge base, shipped with the package
    swapc_tiers.json   Cost tiers, SWaP tiers, evidence grades, postures
    aors.json          6 CCMDs + median threat cost, engagement rate, resupply difficulty
    uas_classes.json   Groups 1-5 + median threat cost, affordable defeat ceiling
    mission_threads.json  8 threads + salvo size, exchange target, attritability priority
    equipment.json     30 systems, attritable-first, with provenance fields
  models.py            Frozen dataclasses and domain exceptions
  taxonomy.py          NEW: tier assignment from equipment figures
  cost_model.py        NEW: rounds/defeat, cost/defeat, exchange, magazine, replenishment
  knowledge_base.py    Loader + section-chunked corpus builder
  retriever.py         Hybrid BM25 + expansion + section boost + MMR
  recommender.py       Hard gates, posture scoring, effector/enabler/baseline split
  report_pdf.py        reportlab PDF (7 sections)
  report_xlsx.py       openpyxl workbook (9 sheets)
  cli.py               Entry point
tests/                 32 pytest cases
```

## Catalog composition

30 systems, deliberately weighted low. Attritable segment: Merops/AS3, TYTAN EOS and METIS, Frankenburg Mark I, Alpine Eagle Sentinel, General Cherry Bullet, Atreyd drone wall, Neros Bandit and Archer, APKWS/VAMPIRE, acoustic mesh nodes, MyDefence Wingman, Echodyne EchoGuard, Firestorm Tempest, AEVEX Atlas. Five systems are flagged `baseline_comparator` (Coyote Blk2, Roadrunner-M, Leonidas, V-BAT) and appear only as comparison.

Epirus Leonidas is retained deliberately as the instructive counter-case: worst unit cost in the catalog ($12M), but best cost per defeat once amortized across a deep magazine. Unit-cost filtering alone would wrongly discard it. The exchange model catches it.

## Data provenance

Every entry carries `cost_confidence` (published / estimated / order_of_magnitude), `as_of`, and `source_note`. The Provenance sheet colors order-of-magnitude entries red and published entries green. Watch Items in both reports flag unverified performance, startup vendor risk, unfavorable exchange, and replenishment shortfalls.

**Refresh before use.** Attritable pricing moves monthly. Roughly a third of the catalog is order-of-magnitude placeholder, clearly labeled. Verify against vendor quotes and program-office data before any acquisition decision.

## Verification

```bash
ruff check .        # zero violations, zero suppressions
ruff format --check .
mypy                # strict mode, clean
pytest              # 32 passed
```

CI runs all four on Python 3.10, 3.11, and 3.12, plus an end-to-end CLI smoke test that asserts both output files are produced.

Tests include ground-truth economics checks: a ~$15K interceptor against a ~$40K Shahed must score favorable; a $125K round against the same threat must not; the HPM must beat the turbojet interceptor on cost per defeat despite 96x the unit cost.
