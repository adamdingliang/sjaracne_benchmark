# Eligible-source predictions: Fig. 6a-style plots

Combined and individual TP, EPR and ROC panels use the reconstructed legacy baseline. Full SIG inference and frozen perturbation-response labels are unchanged. This is neither an exact Fig. 6a reproduction nor a before/after comparison.

TP/EPR use saved 1,000-edge checkpoints plus full-pool endpoints, preserving saved MI tie order. Dashed TP curves are the actual R seed-1 eligible-only rank shuffle. EPR = TP / shuffled TP. No EPR at k=0 is invented and neither network is padded beyond its emitted eligible pool.

ROC is independently recounted from consensus MI, retaining ties. Only emitted eligible pairs enter its denominators, with no omitted bottom-score group. The gray diagonal is the random expectation, not the realized shuffled ROC. Response-reference nonmembers are operational negatives, not established biological negatives.

| Consensus p_c | Eligible edges | Positive matches | AUROC |
|---:|---:|---:|---:|
| 0.01 | 42,067 | 17,727 | 0.622142 |
| 0.001 | 26,667 | 11,647 | 0.609177 |

Panel arrangement follows [scMINER Figure 6a](https://www.nature.com/articles/s41467-025-59620-6). PNG files are raster figures; SVG files retain vector lines and editable text.
