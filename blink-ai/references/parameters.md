# BLINK_c parameters

Run the `parameters` command for the machine-readable catalogue. Prefer the [JSON configuration](configuration.md) for full analyses.

| Native option | Configuration or command | Behavior |
|---|---|---|
| `--file`, `--out` | `input.path`, `output.run_dir` | Input location and a new output directory. |
| `--vcf`, `--uvcf`, `--zvcf` | `input.format` | Import plain or gzip-compressed VCF hard calls. |
| `--hapmap`, `--plink`, `--numeric`, `--binary` | `input.format` | Import the corresponding genotype representation. |
| `--compress`, `--recode` | `convert` | Use the skill's conversion command for import and export with metadata. |
| `--multi` | `input.layout="multi"` | Merge complete chunks before genome-wide GWAS. |
| `--gwas` | `run` | Run BLINK_c and validate the complete per-SNP table. |
| `--glm` | `engine.model="GLM"` | Run the initial covariate-adjusted scan. |
| `--trait` | `engine.trait` | Default 1. Use 0 for all traits or specify names in `phenotype.traits`. |
| `--cycle_size` | `engine.cycle_size` | Positive initial SNP block size, default 2,000. BLINK_c halves a failing block in the same process. |
| `--max_loop` | `engine.max_loop` | Maximum iteration count, default 10. Applies to BLINK. |
| `--bin_size` | `engine.bin_size` | Up to 30 positive values in megabases. The first value determines the active bin map. The default of `1e-6` equals 1 bp. |
| `--bin_selection` | `engine.bin_selection` | `null` keeps the native initial cap. Otherwise, supply up to 100 positive integers. The first value determines the initial cap. |
| `--prior` | `engine.prior` | Up to 100 retained SNP IDs or 1-based post-QC indices. Their initial P values are set to `1e-100` for candidate selection. |
| `--cov` | `engine.cov` | Use 1 to include covariates in each iteration or 2 to include them only in the initial scan. An intercept is automatic. |
| `--cutoff` | `engine.cutoff` | Internal candidate-screening cutoff. Report significance is controlled by `report.alpha`. |
| `--keep` | `samples.keep` | Select samples by ID and retain matching metadata. |
| `--noimp` | `convert`, `qc.genotype_missing` | Preserve missing calls during conversion. For GWAS, use the default rejection policy or explicitly enable mode imputation. |

The available GWAS models are BLINK and GLM. PCA, GPU processing, and parallel execution are unavailable in these executables. Supply precomputed PCs through `covariates` and set phenotype paths and missingness rules in JSON. The interface validates supported keys, ranges, and list lengths.
