# SysGenA input validation: 2026-11-07

The user supplied all three original Synapse input ZIPs. All 15 expression/genotype pairs and gold networks pass validation through both archive and extracted-source routes. Fifteen separate SJARACNe expression inputs and all-gene source lists were prepared externally.

Passed checks:

- 8 SysGenA preparation tests, 6 gold tests and 9 Network 4 regression tests (23 total).
- CRC and recorded archive/member hashes; all 30 extracted originals remain byte-identical.
- Independent exact comparison of all 6,995,000 expression tokens after transpose, 15,000 source-list entries and 6,995 sample-ordinal mappings.
- All generated output and provenance hashes; gene/profile ordering and full 1,000-gene universes.

Source sample IDs are absent. Row correspondence is positional only; no biological identity check is claimed. Input ZIP hashes are locally observed values, not independently compared remote checksums. No inference, scoring or parameter tuning was launched. Raw sources and prepared matrices remain outside Git.

[Current preparation receipt](../../benchmarks/dream5_systems_genetics_a/input_preparation_2026-11-07.json) binds the code and source metadata. [checks.json](checks.json) records validation. The earlier gold-only validation remains a historical pre-acquisition snapshot.

The pre-existing frozen-import mismatch for `benchmarks/brca100_hub_size_dpi_analysis/README.md` remains unchanged (same current hash recorded in the prior data-addition validation). This update does not rewrite that file or its historical manifest.
