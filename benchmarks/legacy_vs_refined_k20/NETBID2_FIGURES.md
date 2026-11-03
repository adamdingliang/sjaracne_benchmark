# Original NetBID2 QC figures

[Process](README.md) · [Results and tables](RESULTS.md)

Left: genuine historical legacy with original p_c=1e-5 consensus. Right:
refined workflow with K20. Each PNG is byte-identical to the image extracted
from its completed NetBID2 HTML. Large HTMLs remain in the original local run
archive; figure and source-HTML hashes are retained in
[report provenance](evidence/report_data.json) and the
[package manifest](evidence/package_manifest.json).

Target-size distributions include **active hubs only**. The results table's
all-hub medians additionally include zero-target candidate hubs. The scale-free
diagnostic uses smoothed incident-node total degrees, not specifically TF
out-degree. Its adjusted R2 describes a fitted distribution, not biological
accuracy. In these figures the x-axis `k` denotes node degree, **not consensus K**.

## BRCA100 TF

| Target-size distribution: legacy | Target-size distribution: refined K20 |
| --- | --- |
| ![BRCA TF legacy targets](figures/netbid2/BRCA100_TF_legacy_historical__a6b251f7863c__target_sizes.png) | ![BRCA TF refined targets](figures/netbid2/BRCA100_TF_current_K20__091973dae267__target_sizes.png) |

| Scale-free diagnostic: legacy | Scale-free diagnostic: refined K20 |
| --- | --- |
| ![BRCA TF legacy scale-free fit](figures/netbid2/BRCA100_TF_legacy_historical__a6b251f7863c__scale_free.png) | ![BRCA TF refined scale-free fit](figures/netbid2/BRCA100_TF_current_K20__091973dae267__scale_free.png) |

## BRCA100 SIG

| Target-size distribution: legacy | Target-size distribution: refined K20 |
| --- | --- |
| ![BRCA SIG legacy targets](figures/netbid2/BRCA100_SIG_legacy_historical__9b2c1318b13e__target_sizes.png) | ![BRCA SIG refined targets](figures/netbid2/BRCA100_SIG_current_K20__b72f3000b8e6__target_sizes.png) |

| Scale-free diagnostic: legacy | Scale-free diagnostic: refined K20 |
| --- | --- |
| ![BRCA SIG legacy scale-free fit](figures/netbid2/BRCA100_SIG_legacy_historical__9b2c1318b13e__scale_free.png) | ![BRCA SIG refined scale-free fit](figures/netbid2/BRCA100_SIG_current_K20__b72f3000b8e6__scale_free.png) |

## LUAD517 TF

| Target-size distribution: legacy | Target-size distribution: refined K20 |
| --- | --- |
| ![LUAD TF legacy targets](figures/netbid2/LUAD517_TF_legacy_historical__fba5536e2aab__target_sizes.png) | ![LUAD TF refined targets](figures/netbid2/LUAD517_TF_current_K20__12a1138ca165__target_sizes.png) |

| Scale-free diagnostic: legacy | Scale-free diagnostic: refined K20 |
| --- | --- |
| ![LUAD TF legacy scale-free fit](figures/netbid2/LUAD517_TF_legacy_historical__fba5536e2aab__scale_free.png) | ![LUAD TF refined scale-free fit](figures/netbid2/LUAD517_TF_current_K20__12a1138ca165__scale_free.png) |

## LUAD517 SIG

| Target-size distribution: legacy | Target-size distribution: refined K20 |
| --- | --- |
| ![LUAD SIG legacy targets](figures/netbid2/LUAD517_SIG_legacy_historical__723995d6a939__target_sizes.png) | ![LUAD SIG refined targets](figures/netbid2/LUAD517_SIG_current_K20__0f28beabfb3e__target_sizes.png) |

| Scale-free diagnostic: legacy | Scale-free diagnostic: refined K20 |
| --- | --- |
| ![LUAD SIG legacy scale-free fit](figures/netbid2/LUAD517_SIG_legacy_historical__723995d6a939__scale_free.png) | ![LUAD SIG refined scale-free fit](figures/netbid2/LUAD517_SIG_current_K20__0f28beabfb3e__scale_free.png) |

## BLCA406 TF

| Target-size distribution: legacy | Target-size distribution: refined K20 |
| --- | --- |
| ![BLCA TF legacy targets](figures/netbid2/BLCA406_TF_legacy_legacy_pc__89aec6ecb309__target_sizes.png) | ![BLCA TF refined targets](figures/netbid2/BLCA406_TF_current_K20__bc272be929c8__target_sizes.png) |

| Scale-free diagnostic: legacy | Scale-free diagnostic: refined K20 |
| --- | --- |
| ![BLCA TF legacy scale-free fit](figures/netbid2/BLCA406_TF_legacy_legacy_pc__89aec6ecb309__scale_free.png) | ![BLCA TF refined scale-free fit](figures/netbid2/BLCA406_TF_current_K20__bc272be929c8__scale_free.png) |

## BLCA406 SIG

| Target-size distribution: legacy | Target-size distribution: refined K20 |
| --- | --- |
| ![BLCA SIG legacy targets](figures/netbid2/BLCA406_SIG_legacy_legacy_pc__764e4691f3d6__target_sizes.png) | ![BLCA SIG refined targets](figures/netbid2/BLCA406_SIG_current_K20__30650e5bcd31__target_sizes.png) |

| Scale-free diagnostic: legacy | Scale-free diagnostic: refined K20 |
| --- | --- |
| ![BLCA SIG legacy scale-free fit](figures/netbid2/BLCA406_SIG_legacy_legacy_pc__764e4691f3d6__scale_free.png) | ![BLCA SIG refined scale-free fit](figures/netbid2/BLCA406_SIG_current_K20__30650e5bcd31__scale_free.png) |
