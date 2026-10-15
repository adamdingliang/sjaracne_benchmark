# DREAM5 Network 3: dataset-readiness results

**Dataset integration only. No SJARACNe inference comparison has been run.**

The cached source archive matches the published MD5, and the bundled source
files are byte-identical to the selected ZIP members. Independent source
inspection established these dimensions and counts:

| Quantity | Count |
| --- | ---: |
| Expression profiles | 805 |
| Released genes | 4,511 |
| Supplied candidate TFs | 334 |
| Explicitly labeled directed non-self pairs | 152,280 |
| Reference-positive pairs | 2,066 |
| Operational reference-negative pairs | 150,214 |
| Sources in the labeled reference | 141 |
| Target nodes in the labeled reference | 1,081 |
| Other candidate-TF-to-gene pairs, **unlabeled** | 1,354,060 |

All 3,631,355 expression entries are finite. Gene and TF IDs are unique;
all TFs and all reference endpoints occur in expression. Reference pairs are
unique, binary-labeled and non-self. The supplied reference agrees with the
official archive's positive-edge-only file and its scoring-universe rules.

The preparation workflow preserves all genes, profiles and TFs and transposes
original numeric strings without normalization or precision changes. Generated
inputs stay under ignored `runs/`; they are not native-network predictions.

## Checks performed on 2026-10-15

- All nine Network 3 checks passed (eight synthetic tests and one bundled
  source-manifest integrity test). The existing six Network 1 checks also passed.
- Bundled-input verification and a real-data preparation run completed
  successfully. The compact execution record is preserved as
  [preparation_check_2026-10-15.json](preparation_check_2026-10-15.json).
- The prepared `.exp` has SHA256
  `a8ea101efa68ae9f047ad5ae4d625e5ddb3b8d03eb6757407c332c46397409f9`;
  the generated 334-TF hub file is byte-identical to the original TF list.
- An independent read-only comparison checked all 3,631,355 generated numeric
  tokens, every gene/profile position and the input header against the original
  transpose, with exact agreement. All seven bundled source/README files also
  matched their exact archive members and manifest hashes/sizes.
- The historical scientific migration and engine-archive integrity checks
  passed. No Network 1, THP-1 or SJARACNe engine files were changed.

The execution record retains its original local paths. Large generated inputs
remain in `runs/dream5_network3_prepared_20261015/`, not in this Git package.

For process, commands and caveats see [README.md](README.md). Source identities
and checksums are in [data/provenance.json](data/provenance.json).
This readiness report is not evidence that sampling changes improve Network 3.
