# Licensing and attribution status

This initial repository is private. No blanket MIT, BSD, GPL or other new license is assigned to the imported materials.

The SJARACNe source repository carries a Columbia software-evaluation license, preserved as `provenance/licenses/SJARACNe_LICENSE.md`. The native engine, original consensus implementation, binaries and native sampling patch are not vendored here. Keeping an engine external does not establish unrestricted rights to every imported benchmark file; provenance and rights review remain necessary before public release.

The later `engine_performance/` archive copies engineering tools, historical
reports and synthetic fixtures from pinned SJARACNe Git objects. Its separate
`provenance/engine_archive_manifest.json` records their source identities; it
does not assign them a new license or change this repository's private status.

Dataset and third-party terms are separate:

- DREAM5 attribution/source-data terms remain in `benchmarks/dream5_network1/DATA_LICENSE.md`; original source files and their checksums are retained.
- The later E. coli Network 3 addition has its own `benchmarks/dream5_network3/DATA_LICENSE.md` and byte-preserved source-member manifest. It uses the same DREAM5 source archive and retains that archive's attribution and host-listed terms; no new blanket license or endorsement is asserted.
- THP-1 uses public GEO `GSM6858449` / `GSE221321`, the scMINER paper/source-data workbook and pinned analysis resources. Resource URLs and revisions remain in the imported `source_pins.json` and fetch helpers. The reference is reconstructed perturbation response, not direct-edge truth or exact numerical reproduction.
- SuperCell, scran, scater, NetBID2 and other dependencies are not relicensed by this repository. Dependency environments/install scripts do not transfer their licenses to the benchmark results.
- TCGA LUAD acquisition requests open GDC expression files. Open-access status is not a replacement for dataset attribution or applicable reuse terms.

Before making the repository public: classify authorship/rights for imported code and documentation, review representative HTML/notebook/source-data outputs, preserve required notices and decide which data/artifacts to distribute. Do not infer legal clearance from a file already being present in another repository.
