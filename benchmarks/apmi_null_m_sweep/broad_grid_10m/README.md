# Broad-grid calibration planning and timing

**Not launched.** On October 15, 2026, the user requested a prospective grid
of m=50..10000 in steps of 50 with 10M fitting plus 10M validation draws,
then explicitly chose to stop after timing and the detailed protocol.

- [Detailed prospective protocol](PROTOCOL.md): 200 sizes, eight probability
  levels through 1e-7, user-approved 10% relative null-rate error target,
  sealed validation/test-m design and candidate function families.
- [Measured runtime and capacity](TIMING.md): small timing draws only, excluded
  from scientific calibration. Full sweep storage would be 32 GB decimal.
- The [completed 19-size study](../expanded_10m/RESULTS.md) remains separate
  and unchanged. No new accepted models, smooth functions or engine defaults
  have been produced by this planning work.

The existing fixed q=0.995 GPD tail cannot cover p=0.05 or 0.01. A single
GPD across this broader range is a hypothesis to test, alongside empirical
body/tail and quantile-surface alternatives. At 10M validation draws,
p=1e-7 yields only one expected event and cannot establish 10% accuracy.
