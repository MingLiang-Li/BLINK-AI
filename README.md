<div align="center">

# BLINK-AI

**Genotype merging, format conversion, and large-scale GWAS — guided by your AI agent.**

For Codex, Claude Code, TRAE, and compatible hosts.

[Download the skill](releases/blink-ai-v0.2.8-macos-arm64-windows-x86_64.zip) · [Usage guide](blink-ai/references/usage.md)

</div>

## Start with a link or ZIP

Give your agent this repository link or the downloaded skill ZIP and ask:

> Read BLINK-AI from the repository link or ZIP I provided. Download or extract the complete skill, read SKILL.md and the full GWAS R template, check the required environment, and use BLINK-AI for my analysis. Install it in this project's skill directory for future sessions.

The agent needs access to local files and command execution, **Python 3.9+**, and **R**. It can prepare the required R packages automatically. Native executables are included for **macOS ARM64** and **Windows x86-64**. Reading the web page alone does not download the analysis tools; ask the agent to retrieve the complete skill.

## Main features

| Feature | What BLINK-AI does |
|---|---|
| **Merge genotype files** | Combine chromosome or numbered chunks after checking sample identity, sample order, and SNP IDs. Merge before fitting one genome-wide model. |
| **Convert formats** | Convert among PLINK binary, VCF, VCF.gz, Numeric, HapMap, and BLINK, preserving supported hard calls and metadata. |
| **Large-scale GWAS** | Run native BLINK or GLM with QC, multiple traits, covariates, sample selection, and configurable model parameters. SNP blocks start at 2,000 and shrink automatically on recoverable block workspace allocation failures. |
| **Plots and reports** | Produce GAPIT Manhattan and QQ plots, Bonferroni/BH-adjusted results, analysis reports, and reproducible run records. |

BLINK_c handles conversion, merging, and GWAS. Bundled GAPIT functions handle phenotype simulation and plotting. [Format requirements](blink-ai/references/format-conversion.md) and [all model settings](blink-ai/references/parameters.md) are documented separately.

## Use your own files

Give the agent your genotype, phenotype, and covariate paths. Input data and generated outputs stay in your analysis project; this repository and skill package contain runtime resources only.

**Merge genotype files**

> Use BLINK-AI to merge the numbered genotype chunks in my genotypes folder into one BLINK dataset. Check sample identities and order, duplicate SNP IDs, and missing calls. Preserve the metadata, report the output location, and stop before GWAS.

**Convert formats**

> Use BLINK-AI to convert my genotypes.vcf.gz to PLINK binary. Preserve sample IDs, coordinates, alleles, and genotype calls, and save the conversion report and metadata sidecars.

**Run a genome-wide analysis**

> Use BLINK-AI to analyze Height in my phenotypes.tsv with the genotype chunks in genotypes and PC1–PC3 from covariates.tsv. Check sample alignment, apply MAF ≥ 0.01, exclude missing phenotypes, and run one merged genome-wide BLINK model. Use an initial SNP block size of 2,000 with native memory adaptation. Save corrected results, GAPIT Manhattan and QQ plots, and the analysis report in runs/height.

Open the generated `report.html` or `report.md` to review your analysis.

## Learn more

[Detailed usage](blink-ai/references/usage.md) · [Configuration](blink-ai/references/configuration.md) · [Troubleshooting](blink-ai/references/diagnostics.md) · [Feedback](blink-ai/references/feedback.md)

macOS workflows have been tested end to end. Windows binaries have architecture and integrity checks; Windows runtime validation remains pending. The distribution includes native binaries without BLINK algorithm C source.

**Written by:** Mingliang Li  
**Designed by:** You Tang, Meng Huang, Zhiwu Zhang

For BLINK analyses, cite [the BLINK publication](https://doi.org/10.1093/gigascience/giy154). Bundled GAPIT components retain their attribution and license; see [third-party notices](THIRD_PARTY_NOTICES.md).
