> Publication copy of a frozen local report/process. Scientific text and numbers are unchanged; relative links are adapted to this compact package. See [publication provenance](PUBLICATION.json) for original hashes and [local artifacts](README.md#local-artifacts) for omitted sidecars.

# TCGA-LUAD gene-level preparation

Prepared 517 patient-distinct primary tumors from 540 validated downloads.
Selection is deterministic, not a claim that a chosen aliquot is biologically superior.

TPM is tpm_unstranded. Every source gene is retained in the TPM/log matrices; N_* summary rows are excluded.
All-zero genes are excluded from the global IQR threshold population. All other gene types remain eligible.
The filtered matrix uses log2(TPM+1), strict IQR > global median, OR TF/SIG IQR > global tenth percentile.
Quantiles are linear/R type 7. TF/SIG membership is frozen before filtering. No symbol collapse, extra low-expression filter, quantile normalization or inference.

Global general IQR cutoff: 0.25471496797691823
Global regulator IQR cutoff: 0

Retained genes: 29841; TF: 1929; SIG: 9464; common: 477.

LUAD_filtered.exp and TF.txt/SIG.txt are aligned by stable Ensembl gene ID; geneSymbol is an annotation.
Do not regenerate IQR filtering for smaller hub panels. No 100-patient benchmark cohort or dynamic epsilon anchor is selected here.

See gene_qc.tsv, regulator_mapping.tsv, samples.tsv, download_selection.tsv, input_validation.tsv and manifest.json for decisions and provenance.
