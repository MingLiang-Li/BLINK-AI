# Using BLINK-AI

BLINK-AI is a domain skill for an agent with access to your project and local programs. The agent turns your request into a checked analysis; BLINK_c performs conversion, merging, and association testing. R and the bundled GAPIT functions handle phenotype simulation, plots, and result summaries.

## Install and check

Install Python 3.9+ and R. Extract the skill ZIP and copy the complete `blink-ai` folder into your project:

| Host | Project directory |
|---|---|
| Codex | `.agents/skills/blink-ai` |
| Claude Code | `.claude/skills/blink-ai` |
| TRAE | `.trae/skills/blink-ai` |

Open a new session in that project. If the host does not discover the skill, ask it to read that folder's `SKILL.md` explicitly. Hosts need permission to read your data and execute local programs. A chat interface without command execution can help prepare an analysis, but cannot run this local workflow by itself.

The GitHub repository also includes `install_BLINK_AI.py`. From the repository directory:

```bash
python3 install_BLINK_AI.py --host codex --project ../my-project
```

Use `--host claude`, `--host trae`, or `--host all` as needed. For Windows commands, replace `python3` with `python` or `py -3`. The same skill folder contains both macOS ARM64 and Windows x86-64 binaries; the runner selects the matching platform.

In the commands below, replace `SKILL_DIR` with the installed folder. Run them from your analysis project:

```bash
python3 "SKILL_DIR/scripts/blinkc_runner.py" setup-environment --project-root .
python3 "SKILL_DIR/scripts/blinkc_runner.py" inspect-environment --profile gwas --project-root .
```

Setup installs missing `jsonlite` into `.blink-ai/r-library/`. GAPIT plotting and simulation functions are bundled. If discovery fails, set `BLINK_AI_RSCRIPT` to your Rscript executable. See [environment settings](configuration.md#r-environment-and-plotting) for offline setup and library overrides.

## Analyze your own data

Tell the agent the genotype files, phenotype table, trait names, covariates, and output location:

> Use BLINK-AI to analyze Height and Yield in phenotype.tsv with genotypes.vcf.gz and PC1–PC3 from covariates.tsv. Check sample IDs and genotype missingness, apply MAF ≥ 0.01, run BLINK, and report Bonferroni-significant results with GAPIT plots. Save the run in runs/height-yield.

The agent must read the full [GWAS R template](../assets/templates/BLINK_AI_GWAS_template.R) before adapting the JSON. For a manual analysis, create a configuration:

```bash
python3 "SKILL_DIR/scripts/blinkc_runner.py" init-config --output analysis.json
```

Edit the generated file, or use this minimal configuration:

```json
{
  "input": {
    "format": "vcf_gz",
    "path": "genotypes.vcf.gz"
  },
  "phenotype": {
    "path": "phenotype.tsv",
    "id_column": "sample_id",
    "traits": ["Height", "Yield"],
    "missing": "exclude_per_trait"
  },
  "covariates": {
    "path": "covariates.tsv",
    "id_column": "sample_id",
    "columns": ["PC1", "PC2", "PC3"]
  },
  "engine": {"model": "BLINK", "cycle_size": 2000},
  "qc": {"maf_min": 0.01, "genotype_missing": "reject"},
  "output": {"run_dir": "runs/height-yield"}
}
```

Paths resolve relative to the JSON file. Phenotype and covariate tables need a header and unique sample IDs. IDs are matched explicitly; table row order is not a substitute for identity. Covariates must be complete and the model matrix must have full rank. For an analysis without covariates, omit the `covariates` section.

```bash
python3 "SKILL_DIR/scripts/blinkc_runner.py" run --config analysis.json
```

The default rejects missing genotypes. To impute explicitly, set `qc.genotype_missing` to `mode`. Missing phenotype tokens include blank, `NA`, `NaN`, and `.`; **`-9` is treated as a number**. Review [configuration](configuration.md) before choosing a missingness policy.

### Multiple genotype files

Set the input to a directory with `"layout": "multi"`. Every chunk must use the same sample IDs and order, with unique SNP IDs across chunks. Filenames need unique leading integers, such as `001_chr01.vcf.gz` and `002_chr02.vcf.gz`.

```json
"input": {"format": "vcf_gz", "layout": "multi", "path": "genotypes"}
```

This is a configuration excerpt. BLINK-AI converts and filters each chunk, merges the retained data, then runs one genome-wide model. It does not fit a separate conditional model to each chunk.

### Tune the native model

Use `engine.model="GLM"` for the initial covariate-adjusted scan. BLINK also exposes iteration limits, bin sizes, candidate limits, prior SNPs, covariate handling, and the internal screening cutoff. Run `parameters` or read the [parameter catalogue](parameters.md) for the effective behavior of every supported setting.

`engine.cycle_size` starts at 2000. When a recoverable block workspace allocation fails, BLINK_c halves the effective block size, rounds down, and retries the unfinished block in the same process. This mechanism does not recover an operating-system process kill or every possible allocation failure.

## Convert formats

> Use BLINK-AI to convert my VCF.gz to PLINK binary. Preserve sample IDs, allele labels, coordinates, and missing calls. Save the conversion report and metadata sidecars.

```bash
python3 "SKILL_DIR/scripts/blinkc_runner.py" convert --from vcf_gz --to plink --input genotypes.vcf.gz --output-dir runs/plink
```

All directions are supported among `plink`, `vcf`, `vcf_gz`, `numeric`, `hapmap`, and `blink`, within the [hard-call format contract](format-conversion.md). For PLINK, Numeric, and BLINK, pass the shared filename prefix. Outputs use `output/data` inside the selected directory; retain the generated sidecars.

For example, convert a PLINK output back to VCF.gz:

```bash
python3 "SKILL_DIR/scripts/blinkc_runner.py" convert --from plink --to vcf_gz --input runs/plink/output/data --output-dir runs/vcf
```

VCF phase and annotations require explicit `--allow-lossy` before they can be dropped. Numeric input may need `--samples` and `--alleles`. Conversion is sequential per dataset; `cycle_size` controls GWAS blocks, not conversion speed. See [performance](performance.md) for stage timings and practical storage advice.

## Simulate and evaluate

Enable simulation only when requested and supply the user's genotype file. Omit `phenotype.path`, then set `simulation.enabled=true` and choose the seed, heritability, and number of causal SNPs. For example:

```json
{
  "input": {"format": "vcf_gz", "path": "genotypes.vcf.gz"},
  "simulation": {"enabled": true, "seed": 20261105, "h2": 0.75, "nqtn": 10},
  "output": {"run_dir": "runs/simulation"}
}
```

Save the configuration in the analysis project and run it with the standard `run --config` command. GAPIT generates phenotypes from that input; the workflow writes simulation data and evaluation outputs in the chosen run directory. See [simulation settings](configuration.md#simulation).

## Read and troubleshoot a run

| File | Use |
|---|---|
| `report.html`, `report.md` | Start here for the analysis summary and linked outputs. |
| `results/gwas.tsv` | All tested SNPs, P values, MAF, coordinates, and traits. |
| `results/adjusted.tsv`, `results/significant.tsv` | Per-trait Bonferroni and BH correction; selected significant SNPs. |
| `plots/` | GAPIT Manhattan (`Oceanic`) and QQ (`rainbow`) PDFs. |
| `manifest.json`, `context.json` | Status, exact commands, hashes, sample alignment, QC, and block reductions. |
| `results/plotting.json`, `results/R-session.json` | Plot function provenance and R environment. |
| `logs/` | Stage output and failure details. |

P values indicate association under the fitted model. The native result does not provide effect estimates, standard errors, effect alleles, or variance explained. Precomputed PCs can be supplied; this workflow does not estimate PCs or run GPU or multithreaded native analysis.

For an error, ask:

> Use BLINK-AI to diagnose runs/height-yield. Identify the failed stage, explain the evidence, record my feedback locally, and verify any proposed fix before a new run.

Failures generate local feedback records where possible. User-reported problems and suggestions are recorded in `feedback_data/reports/`, linked to the run and verification evidence. Records stay local unless you submit them. See [troubleshooting](diagnostics.md), [feedback](feedback.md), and [interpretation](genetics.md).

The [official OpenAI installation reference](https://developers.openai.com/api/reference/cli) documents project skill locations for Codex and Claude Code. Host discovery can vary; explicit `SKILL.md` loading remains a practical fallback.
