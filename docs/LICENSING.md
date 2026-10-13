# Licensing and attribution status

This initial repository is private. No blanket MIT, BSD, GPL or other new license is assigned to the imported materials.

The SJARACNe source repository carries a Columbia software-evaluation license, preserved as `provenance/licenses/SJARACNe_LICENSE.md`. The native engine, original consensus implementation, binaries and native sampling patch are not vendored here. Keeping an engine external does not establish unrestricted rights to every imported benchmark file; provenance and rights review remain necessary before public release.

Dataset and third-party terms are separate:

- DREAM5 attribution/source-data terms remain in `benchmarks/dream5_network1/DATA_LICENSE.md`; original source files and their checksums are retained.
- THP-1 uses public GEO `GSM6858449` / `GSE221321`, the scMINER paper/source-data workbook and pinned analysis resources. Resource URLs and revisions remain in the imported `source_pins.json` and fetch helpers. The reference is reconstructed perturbation response, not direct-edge truth or exact numerical reproduction.
- SuperCell, scran, scater, NetBID2 and other dependencies are not relicensed by this repository. Dependency environments/install scripts do not transfer their licenses to the benchmark results.
- TCGA LUAD acquisition requests open GDC expression files. Open-access status is not a replacement for dataset attribution or applicable reuse terms.

Before making the repository public: classify authorship/rights for imported code and documentation, review representative HTML/notebook/source-data outputs, preserve required notices and decide which data/artifacts to distribute. Do not infer legal clearance from a file already being present in another repository.
