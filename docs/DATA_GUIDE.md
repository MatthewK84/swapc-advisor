# Data Maintenance Guide

The catalog is the perishable asset. Code changes are rare; data changes should be routine. This guide covers adding a system, updating prices, and the checks that gate both.

## Adding a system

Append one object to `src/swapc_advisor/data/equipment.json`. Required fields, in schema order:

| Field | Type | Rules |
|---|---|---|
| `id` | string | Unique, lowercase, underscores |
| `name`, `vendor` | string | Display names |
| `vendor_maturity` | enum | `startup`, `scaleup`, `prime` |
| `type` | string | Free-form system class |
| `category` | enum | `counter_uas` or `uas_employment` |
| `mission_threads` | array | Must resolve to ids in `mission_threads.json` |
| `target_groups` | array | DoD groups 1-5 |
| `swap_c` | object | `weight_lb`, `size`, `power_w`, `unit_cost_usd` only |
| `flight_time_min`, `effective_range_km` | number | 0 for ground-based |
| `single_shot_pk` | object | Keys are group numbers as strings, each key must appear in `target_groups`. Empty object = enabler (sensor/C2, no defeat) |
| `uses_per_unit` | int | 1 for expendables; sortie/engagement count for reusables |
| `units_per_month` | int | Stated or estimated production rate |
| `evidence_grade` | enum | `combat_proven`, `fielded`, `demonstrated`, `development`, `concept` |
| `baseline_comparator` | bool | `true` removes it from ranking; it appears only as a POR baseline |
| `environment_tags` | array | Match tags used in `aors.json` for AOR-fit scoring |
| `gps_denied_capable`, `ew_resilient` | bool | — |
| `cost_confidence` | enum | `published`, `estimated`, `order_of_magnitude` |
| `as_of` | string | `YYYY-MM` |
| `source_note` | string | Where the figures came from. Be specific |
| `notes` | string | One-paragraph assessment. BLUF style |

No other fields are permitted. The validator rejects unknown fields by design.

## Estimating Pk honestly

Per-group Pk values are planning assumptions, not test data. Conventions used in the shipped catalog: purpose-built missiles 0.70-0.80, autonomous interceptors 0.55-0.70, FPV-derived interceptors 0.40-0.55, degrade 0.05-0.10 per group step upward (faster, higher targets). If you have real test data, use it and cite it in `source_note`.

## After any edit

```bash
swapc-validate   # schema, cross-references, enums, dates
pytest           # includes README-claim guards; update README counts if totals changed
```

Both run in CI, so a bad edit cannot merge silently. If you change the system count or the baseline count, update the matching numbers in README.md; the guard tests will fail until the claim and the data agree.

## Updating prices

Change `unit_cost_usd`, bump `as_of`, adjust `cost_confidence` if the source improved, and rewrite `source_note`. Never leave a stale `as_of` on a fresh number.
