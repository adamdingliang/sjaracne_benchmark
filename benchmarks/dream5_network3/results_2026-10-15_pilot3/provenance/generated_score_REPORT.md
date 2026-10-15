# DREAM5 Network 3 exploratory sampling pilot

Primary endpoint: u80 versus legacy nominal post-DPI fixed-explicit-universe average precision.

| Arm | TP | FP | Precision | Sensitivity | Specificity | AUROC | AP |
|---|---:|---:|---:|---:|---:|---:|---:|
| legacy | 206 | 3242 | 0.05974477958236659 | 0.099710 | 0.978417 | 0.539562 | 0.042117 |
| u64 | 217 | 2233 | 0.08745402533714752 | 0.105034 | 0.985135 | 0.545407 | 0.047296 |
| u80 | 200 | 2134 | 0.08785871964679912 | 0.096805 | 0.985794 | 0.541570 | 0.045776 |
| u90 | 203 | 2064 | 0.08874172185430464 | 0.098258 | 0.986260 | 0.542443 | 0.045498 |

Values are medians of three computational resamples. Paired primary AP deltas: [0.0036592090369877706, 0.0047313702754269715, 0.002568146731243469]

- Three exploratory computational resamples, not independent biological replicates or confidence intervals
- Only explicitly labelled directed pairs scored; unlabelled predictions are not false positives
- Undirected MI associations are evaluated against directed gold labels; this is not the official DREAM5 probability-density score
- Stage/control analyses are supporting diagnostics, not evidence selected to guarantee improvement
