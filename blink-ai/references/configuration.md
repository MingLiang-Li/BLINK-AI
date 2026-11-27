# Configure and run an analysis

Read the [GWAS R template](../assets/templates/BLINK_AI_GWAS_template.R) before generating `analysis.json` with `init-config`. Paths in JSON are resolved relative to the configuration file.

| Setting | Meaning |
|---|---|
| `input.path`, `input.format`, `input.layout` | Input file or prefix, genotype format, and `single` or `multi` layout. See [genotype formats](format-conversion.md). |
| `input.samples`, `input.alleles` | Optional sample and variant metadata TSV files. |
| `input.allow_lossy` | Explicitly allow the loss of phase or annotations outside the hard-call representation. The default is `false`. |
| `phenotype.path`, `phenotype.id_column` | Phenotype table with a unique header and unique sample IDs. TSV, CSV, and whitespace delimiters are supported. The first column is the default ID column. |
| `phenotype.traits` | Select traits by name. With `null`, `engine.trait` selects a 1-based trait or all traits with `0`. |
| `phenotype.missing` | Use `exclude_per_trait` or `error`. Blank values, `NA`, `NaN`, `nan`, and `.` are missing. The value `-9` is numeric. |
| `covariates.path`, `covariates.columns` | Covariates matched by sample ID. The design matrix including the intercept must have full rank. Covariates must be complete. |
| `samples.keep` | List of unique sample IDs in the desired order. |
| `qc.maf_min`, `qc.missing_max` | Filters applied after sample selection and before imputation. Defaults are 0.01 and 1.0. |
| `qc.genotype_missing` | The default is `reject`. Explicit `mode` imputation uses the most frequent hard call at each SNP, with ties resolved to the smaller code. An all-missing SNP cannot be imputed. |
| `report.multiple_testing`, `report.alpha` | Use `bonferroni` or `BH`, applied per trait. The default alpha is 0.05. |
| `report.plot_dpp`, `report.plot_seed` | Plot subsampling limit and seed. All retained tests contribute to multiple-testing correction. |
| `runtime.rscript`, `runtime.timeout_seconds` | Optional Rscript path and analysis time limit. |
| `runtime.project_root` | Project root for the R library and feedback. Defaults to the configuration directory. |
| `feedback.user_request`, `feedback.user_experience` | Original user wording and any experience the user has actually reported. Use `null` for unavailable context. |
| `output.run_dir` | A new directory for the run. |

For `input.layout="multi"`, put the chunks in one directory with unique leading numbers, for example `001_chr1.vcf` and `002_chr2.vcf`. Use the same sample IDs and order in every chunk and unique SNP IDs across chunks. BLINK-AI applies quality control to each chunk and merges the retained data before scanning the genome.

## GWAS block size

Set `engine.cycle_size` to a positive integer. The default initial limit is 2,000 SNPs per block. The effective size is capped by the number of SNPs remaining in the scan.

If BLINK_c cannot reserve block workspace or the block exceeds the index range, it halves the effective size, rounds down, and resumes at the current SNP in the same process. Subsequent blocks, iterations, and traits use the reduced limit. The minimum is one SNP. The native log, report, and `gwas_batches` entries in `manifest.json` show the reductions.

## R environment and plotting

The standard `run` command prepares the R dependencies automatically. Run `setup-environment --project-root .` to prepare them separately. Install R when Rscript is unavailable, or set `BLINK_AI_RSCRIPT` to an existing executable. The setup creates `.blink-ai/r-library/` under the project root, isolates packages by R version and platform, and installs missing `jsonlite` from CRAN. Existing compatible packages can be reused.

Set `BLINK_AI_R_LIBRARY` to override the library base, `BLINK_AI_CRAN_MIRROR` to select a CRAN repository, or `BLINK_AI_INSTALL_R_PACKAGES=false` to disable dependency downloads. The setup command also supports `--no-install`. Inspect the resulting environment with `inspect-environment --profile gwas --project-root .`. Setup logs and the R environment record are saved locally.

Manhattan and QQ plots always use the bundled `GAPIT.Manhattan` and `GAPIT.QQ` functions. Their default styles are `Oceanic` and `rainbow`. `results/plotting.json` records the provider, function names, styles, and trait plots. The bundled GAPIT functions are checked against their component hashes before a standard run.

For installation behavior, see the R documentation for [package installation](https://stat.ethz.ch/R-manual/R-devel/library/utils/html/install.packages.html) and [library search paths](https://stat.ethz.ch/R-manual/R-devel/library/base/html/libPaths.html).

## Simulation

Set `simulation.enabled=true` and omit `phenotype.path` to simulate a quantitative additive phenotype. Set `simulation.seed`, `h2`, `nqtn` (at least two), and `qtn_distribution` (`normal` or `geometry`). The bundled GAPIT settings use equal effects for `geometry`. The default `max_cells` limits the simulation genotype matrix to five million cells.

## Results

- `report.md` and `report.html` summarize the analysis and link to results and plots.
- `results/gwas.tsv` contains per-SNP P values, MAF, and coordinates. `results/adjusted.tsv` adds Bonferroni-adjusted P values, BH-adjusted P values, and the significance flag. `results/significant.tsv` contains the flagged SNPs.
- `plots/` contains Manhattan and QQ PDFs for each trait. `results/traits.json` maps plot names to trait labels and records sample counts.
- `manifest.json` records status, commands, executable and output hashes, and block-size changes. `context.json` records input identity, alignment, chromosome mapping, and QC. The run retains the resolved configuration and R template for reproducibility.
- Simulated analyses also produce phenotype, causal SNP, effect component, and evaluation tables under `simulation/`.

The analysis report summarizes results. User feedback is recorded separately under the project root in `feedback_data/reports/`, with the run ID and evidence references. See [feedback reporting](feedback.md).

Phenotypes are modeled as numeric values. Choose coding and a model appropriate to the trait before analyzing categorical data.
