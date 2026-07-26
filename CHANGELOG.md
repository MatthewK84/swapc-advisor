# Changelog

## 2.1.0 (2026-07-26)

**Modeling**
- Per-threat-group Pk replaces the scalar. Planning uses the worst relevant group, because a round that is 0.70 against a hovering quadcopter is not 0.70 against a Shahed at 185 km/h. This was the largest silent simplification in 2.0 and it fed directly into the headline cost-per-defeat metric.
- `--asset-value` adds the defended asset to the exchange numerator (threat cost plus asset value times an assumed 0.25 damage probability). Defeating a $3K FPV that would mission-kill a $40M aircraft is now scored as denying far more than $3K, which is why NORTHCOM and SOUTHCOM recommendations previously looked economically irrational when they were operationally correct.

**Decision quality**
- Deterministic sensitivity analysis: a 3x3 grid perturbs cost +/-50% and Pk +/-0.15, re-ranks under all nine scenarios, and reports rank stability. An unstable top pick now triggers an explicit BLUF caution to treat the leaders as a trade space.
- Layered architecture proposal: best passing effector per outer/mid/terminal band plus the best enabler, with combined magazine cost and leakage probability.

**Integrity**
- `swapc-validate` console command: cross-references, enumerations, dates, Pk-key consistency, duplicate ids, posture weight sums, and strict unknown-field rejection. The unknown-field check exists because schema drift was observed landing silently in the catalog during development.
- README-claim guard tests: every countable claim in the README is asserted against the shipped code in CI. Added after two README numbers drifted from the data.

**Catalog**
- Two INDOPACOM-relevant additions (Anduril Barracuda-100M, PteroDynamics Transwing X-P4) and maritime/salt-fog tags where physically justified, raising INDOPACOM environment coverage from 16/30 to 23/32.

**Fixes**
- README claimed five baseline comparators; the data has four.
- README claimed a 30-entry retrieval lexicon; it had 25. The lexicon now has 30 entries (maritime, salvo, sensor, loitering, resupply added) and the count is test-enforced.

## 2.0.0 (2026-07-25)

Attritable-first redesign. v1 ranked on unit cost, mission fit, and a fielding-maturity bonus that systematically rewarded programs of record: a CENTCOM OWA query returned a $500K recoverable interceptor. v2 returns a $3K round at 23x lower cost per defeat, with the POR shown only as the baseline it beats.

- Cost-exchange model (cost per defeat vs threat cost) replaces unit-cost ranking.
- Two-axis tier classification: T0 Consumable through T4 Exquisite, S0 Pocket through S4 Fixed Site, auto-assigned from equipment figures.
- Maturity bonus inverted into a tier penalty under the default posture.
- Programs of record separated into a baseline comparison set.
- Production rate scored: magazine cost and replenishment days reported.
- Effectors separated from enablers, with a recommended sensor pairing in the BLUF.
- RAG rebuilt: domain query expansion, section-chunked corpus with intent boosting, MMR diversification.

## 1.0.0 (2026-07-24)

Initial release: BM25 retrieval, weighted scoring, PDF and Excel reports.
