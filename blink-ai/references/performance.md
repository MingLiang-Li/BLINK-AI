# Conversion performance and resource use

The `convert` command executes sequential stages. Python checks the input structure, metadata, and all hard calls. The native executables normalize and import the genotype data, then export the requested format. The workflow also verifies the imported BLINK data, the final hard calls and metadata, and the file hashes.

The current command uses one conversion process at a time and provides no worker-count or GPU option for an individual file. Setting a GWAS `engine.cycle_size` configures GWAS scanning. It does not select conversion worker counts.

## Inspect elapsed time

Read the `performance` object in `conversion.json`. Its `timings_seconds` values separate the following stages.

| Stage | Work |
|---|---|
| `environment_and_input_validation` | Executable checks and input parsing, metadata and hard-call validation |
| `input_file_hashes` | Input file SHA-256 |
| `staging_and_native_import` | File staging, normalization, and BLINK import |
| `import_hardcall_validation` | Full imported-genotype and BLINK value validation |
| `hub_metadata` | Canonical sample and variant metadata |
| `native_export` | Target genotype encoding and any gzip compression |
| `output_metadata_and_hardcall_validation` | Metadata, sidecars, and all final hard calls |
| `output_file_hashes` | Output file SHA-256 |

The native command records also contain elapsed seconds. These values measure wall time. Check operating-system CPU, memory pressure, and disk activity to identify which resource limits the slow stage.

## Choose a strategy

| Observation | Adjustment |
|---|---|
| Input or hard-call validation dominates | Use the current bulk-validation implementation. For repeated analyses, retain a BLINK conversion and its metadata sidecars as the analysis input. |
| Compressed text export dominates | Choose BLINK or PLINK when suitable for the next analysis step. Write VCF.gz when that representation is needed for sharing or downstream tools. |
| File staging or hashing dominates | Use local storage with sufficient working space. Account for intermediate files as well as final outputs. |
| Several independent files need conversion | Run independent conversion commands concurrently, each with a distinct output directory. Start with two processes and compare elapsed time, memory pressure, and disk activity before increasing concurrency. |
| Memory pressure increases during concurrent runs | Reduce the number of simultaneous conversions. Each process retains metadata and has its own native import buffers. |

For chromosome chunks belonging to one study, keep compatible sample IDs and order so the retained genotype chunks can be merged before genome-wide BLINK analysis.

Python hard-call validation uses bounded byte lookup tables and bulk byte operations. Genotype rows are processed incrementally, while sample and variant metadata are retained for identity checks. Full validation remains enabled in every conversion.
