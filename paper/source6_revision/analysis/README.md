# Layer Agreement uncertainty analysis

`layer_agreement_inference.py` performs a secondary analysis of the frozen
July 1, 2026 equal-share country--measurement table. It does not recollect
traceroutes or rerun corridor projection.

The analysis keeps all units from the same country together. It uses 50,000
within-group country-cluster bootstrap replicates and 100,000 country-label
permutations with seed `20260919`. The generated files in `analysis/results/`
record the 272 non-landlocked units and the resulting intervals and reference
p-value.

The saved projection-score and Top-1 artifacts contain aggregate coefficients
but not the per-unit summaries needed for the same clustered analysis. The
paper therefore reports clustered uncertainty only for equal sharing and
retains the score-weighted and Top-1 results as descriptive comparisons.
