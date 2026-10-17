# BRCA100 PCHIP network-QC results

Inputs are final post-DPI consensus networks from the fresh PCHIP run.
Network metrics use the full supplied driver lists, including zero-target drivers.
Scale-free R2 is NetBID2's adjusted log-degree regression R2, not evidence of edge truth.

- [TF QC HTML](tf_netbid2_qc.html)
- [SIG QC HTML](sig_netbid2_qc.html)
- [Network metrics](network_metrics.tsv)

Download HTML files and open locally: GitHub displays source instead of rendering HTML.
Figures and normal assets are embedded. The standard template may request MathJax online;
offline viewing can omit mathematical typesetting. Verify with `sha256sum -c SHA256SUMS`.

Historical sweep overlap, when present, is a matched-setting cutoff-function comparison:
inputs, seeds, sampling, DPI and consensus settings match, and AP-MI kernel and consensus
source are unchanged. Compiler/runtime equivalence is qualified by the explicit-cutoff
anchor check. These comparisons are descriptive, without biological edge truth.
Network shape cannot establish reliability or a final-network FDR.
