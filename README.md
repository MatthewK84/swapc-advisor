# SWaP-C Down-Selection Advisor

[![CI](https://github.com/MatthewK84/swapc-advisor/actions/workflows/ci.yml/badge.svg)](https://github.com/MatthewK84/swapc-advisor/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](pyproject.toml)

BLUF: Offline, RAG-backed down-selection tool for UAS and counter-sUAS technology, built attritable-first. You supply a mission thread, a cost ceiling, flight requirements, and an AOR. It returns a tier-classified, cost-exchange-justified recommendation with sensitivity analysis and a layered architecture proposal, saved as PDF and Excel.

The design premise: unit cost misranks C-UAS effectors, and program-of-record maturity bonuses systematically bury the attritable systems that win the exchange math. This tool ranks on **cost per defeat** — unit cost amortized over reuses, divided by per-group probability of kill — measured against what the threat costs and what the defended asset is worth.

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

Example output: a $3,000 FPV-derived interceptor at 23x lower cost per defeat than the program-of-record baseline, paired with a $600 acoustic sensor node, a three-layer architecture with combined leakage estimate, and a stability verdict across nine data-uncertainty scenarios.

## Inputs

| Flag | Required | Meaning |
|---|---|---|
| `--mission-thread` | Yes | One of 8 threads (5 C-sUAS, 3 UAS employment) |
| `--cost-threshold` | Yes | Maximum acceptable cost per unit, USD |
| `--flight-time` | Yes | Required flight time, minutes (0 for ground-based) |
| `--distance` | Yes | Required flight distance or engagement range, km |
| `--aor` | Yes | CENTCOM, EUCOM, INDOPACOM, AFRICOM, SOUTHCOM, NORTHCOM |
| `--asset-value` | No | USD value of the defended asset. Raises the exchange numerator by expected damage prevented, so cheap threats against high-value assets justify costlier effectors |
| `--posture` | No | `attritable_first` (default), `balanced`, `capability_first`. Shifts all scoring weights and tier penalties |
| `--max-cost-tier` | No | Hard ceiling, default T4. `--max-cost-tier T1` excludes anything above attritable |
| `--data-dir` | No | Alternate knowledge base directory |

Mission threads: `fixed_site_defense`, `maneuver_force_protection`, `critical_infrastructure`, `maritime_port_defense`, `owa_interdiction`, `isr_recon`, `precision_strike`, `logistics_resupply`.

## How the recommendation works

1. **Retrieve.** Hybrid BM25 over a section-chunked knowledge base: a 30-entry domain lexicon expands operator phrasing ("cheap") to catalog wording ("attritable", "expendable"), section boosting prefers economics chunks for economics queries, and MMR diversification prevents one system from crowding the context. Dependency-free and deterministic, so it runs identically on air-gapped NIPR and SIPR hosts.
2. **Classify.** Every system is auto-assigned a cost tier (T0 Consumable through T4 Exquisite) and a SWaP tier (S0 Pocket through S4 Fixed Site) from its own figures, so labels cannot drift from the catalog.
3. **Gate.** Cost threshold, tier ceiling, flight time, and distance are pass/fail. Ground-based effectors are flight-exempt.
4. **Score.** Seven weighted factors: cost exchange 28%, SWaP efficiency 18%, mission thread fit 15%, AOR fit 12%, threat group coverage 10%, production rate 10%, evidence grade 10% (default posture), then a tier multiplier that penalizes exquisite systems. Pk is per-threat-group; planning uses the worst relevant case, because a round that is 0.70 against a hovering quadcopter is not 0.70 against a Shahed at 185 km/h.
5. **Separate.** Effectors rank against effectors. Sensors rank separately as enablers, and the BLUF recommends a pairing, because attritable interceptors need an external sensor picture to be employable. Program-of-record systems appear only as baselines with an explicit cost-per-defeat delta.
6. **Stress.** A deterministic 3x3 sensitivity grid perturbs cost +/-50% and Pk +/-0.15, re-ranks under all nine scenarios, and reports rank stability. If the top pick survives fewer than two-thirds of scenarios, the BLUF says so and tells you to treat the top candidates as a trade space.
7. **Layer.** An outer/mid/terminal architecture proposal combines the best passing effector per range band with the best enabler, and reports total magazine cost and leakage probability.

## Architecture

```
src/swapc_advisor/
  data/                Knowledge base, shipped with the package
    swapc_tiers.json   Cost tiers, SWaP tiers, evidence grades, postures
    aors.json          6 CCMDs + median threat cost, engagement rate, resupply difficulty
    uas_classes.json   Groups 1-5 + median threat cost, affordable defeat ceiling
    mission_threads.json  8 threads + salvo size, exchange target, attritability priority
    equipment.json     32 systems, attritable-first, with provenance fields
  models.py            Frozen dataclasses and domain exceptions
  taxonomy.py          Tier assignment from equipment figures
  cost_model.py        Per-group Pk, cost/defeat, asset-adjusted exchange, magazine math
  sensitivity.py       Deterministic 9-scenario rank stability analysis
  architecture.py      Layered defense proposal with leakage estimate
  validate.py          Knowledge base validator (swapc-validate)
  knowledge_base.py    Loader + section-chunked corpus builder
  retriever.py         Hybrid BM25 + expansion + section boost + MMR
  recommender.py       Hard gates, posture scoring, effector/enabler/baseline split
  report_pdf.py        reportlab PDF (9 sections)
  report_xlsx.py       openpyxl workbook (11 sheets)
  cli.py               Entry point
tests/                 46 pytest cases, including README-claim guards
docs/                  Sample report and data maintenance guide
```

## Catalog composition

32 systems, deliberately weighted low. Attritable segment: Merops/AS3, TYTAN EOS and METIS, Frankenburg Mark I, Alpine Eagle Sentinel, General Cherry Bullet, Atreyd drone wall, Neros Bandit and Archer, APKWS/VAMPIRE, acoustic mesh nodes, MyDefence Wingman, Echodyne EchoGuard, Firestorm Tempest, AEVEX Atlas, Barracuda-100M, and PteroDynamics Transwing. 4 systems are flagged `baseline_comparator` (Coyote Blk2, Roadrunner-M, Leonidas, V-BAT) and appear only as comparison.

Epirus Leonidas is retained deliberately as the instructive counter-case: worst unit cost in the catalog ($12M), but best cost per defeat once amortized across a deep magazine. Unit-cost filtering alone would wrongly discard it. The exchange model catches it, and a test asserts that it does.

## Data provenance and validation

Every entry carries `cost_confidence` (published / estimated / order_of_magnitude), `as_of`, and `source_note`. The Provenance sheet colors order-of-magnitude entries red and published entries green. Watch Items flag unverified performance, startup vendor risk, unfavorable exchange, and replenishment shortfalls.

```bash
swapc-validate    # cross-references, enums, dates, Pk consistency, unknown-field rejection
```

The validator rejects any field not in the schema allowlist. CI runs it on every push, alongside test guards that assert every countable README claim against the shipped code.

**Refresh before use.** Attritable pricing moves monthly. Roughly a third of the catalog is order-of-magnitude placeholder, clearly labeled. Verify against vendor quotes and program-office data before any acquisition decision. See [docs/DATA_GUIDE.md](docs/DATA_GUIDE.md) for how to add or update systems.

## Verification

```bash
ruff check .        # zero violations, zero suppressions
ruff format --check .
mypy                # strict mode, clean
pytest              # 46 passed
swapc-validate      # knowledge base internally consistent
```

CI runs all five on Python 3.10, 3.11, and 3.12, plus an end-to-end CLI smoke test asserting both output files are produced. Tests include ground-truth economics checks: a ~$15K interceptor against a ~$40K Shahed must score favorable; a $125K round against the same threat must not; the HPM must beat the turbojet interceptor on cost per defeat despite 96x the unit cost; and defending a $40M asset must flip an otherwise-unfavorable exchange.

## History

See [CHANGELOG.md](CHANGELOG.md) for the v1 to v2 redesign rationale and the v2.1 additions.
