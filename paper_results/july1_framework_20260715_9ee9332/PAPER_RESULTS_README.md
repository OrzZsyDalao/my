# Paper Results

Run ID: `july1_framework_20260715_9ee9332`.

## 1. Scope
This package contains only completed measurements listed in this run's index.

## 2. Observation unit
A traceroute is decomposed into measurement-observed atomic path-transition segments.

## 3. Trace denominator
Trace IDs use measurement, probe, timestamp, and actual target IP; transport filenames are excluded.

## 4. Physical projection
Candidates are feasible submarine corridor candidates, not observed cable use.

## 5. Topology
The default policy enumerates valid landing-station pairs on the same cable when only unordered landing metadata is available. These are reachability candidates, labelled unordered_cable_reachability, not asserted direct physical links. Explicit topology can be evaluated separately with the adjacent_only policy.

## 6. Candidate exposure
Exposure means a trace contains at least one atomic segment with a feasible corridor candidate.

## 7. Observation mass
Mass counts traceroute-observed transitions, not traffic volume, packets, or bytes.

## 8. Corridor concentration
Concentration is measured over feasible corridor observation distributions.

## 9. Network concentration
Network transition concentration is computed over the same atomic segment population.

## 10. Cross-layer audit
The audit compares distribution shapes, not AS and corridor counts as interchangeable units.

## 11. Robustness
Sensitivity outputs retain timeout-gap, geolocation, topology, and support uncertainty where available.

## 12. Candidate breadth
Unique corridor counts are candidate-space breadth descriptors, not the primary observation-concentration metric.

## 13. Interpretation boundary
No table establishes real traffic volume, actual cable use, or ground-truth cable attribution.
