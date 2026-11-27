<div align="center">

# BLINK-AI

**AI-assisted genotype merging, format conversion, and large-scale GWAS.**

For Codex, Claude Code, TRAE, and compatible hosts.

[Download the skill](releases/blink-ai-v0.2.9-macos-arm64-windows-x86_64.zip) · [Usage guide](blink-ai/references/usage.md)

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

## Quick start with example data

Download [DEMO_DATA.zip](DEMO_DATA.zip) and extract it into your analysis project. The example data include six genotype chunks in VCF.gz format, phenotype data, and covariates. Give your AI agent the following prompts.

**Merge genotype files**

> Use BLINK-AI to merge the numbered genotype chunks in `vcf_split_iid` into one BLINK dataset. Check sample identities and order, duplicate SNP IDs, and missing calls. Preserve the metadata and report the output location.

**Convert formats**

> Use BLINK-AI to convert the merged genotype dataset to PLINK binary and Numeric formats. Preserve sample IDs, SNP IDs, genomic positions, alleles, and genotype calls.

**Run a genome-wide analysis**

> Use BLINK-AI to perform GWAS for `Faridpur_Aberdeen_phe` in `phenotypes.txt` using the merged genotype dataset and PC1–PC4 from `covariates.cov`. Check sample alignment, apply MAF ≥ 0.01, and run a genome-wide BLINK model. Save corrected association results, GAPIT Manhattan and QQ plots, and the analysis report.

Open the generated `report.html` or `report.md` to review your analysis.

## Use your own files

Give the agent your genotype, phenotype, and covariate paths, and describe your analysis requirements in natural language. Input data and generated outputs stay in your analysis project.

## Learn more

[Detailed usage](blink-ai/references/usage.md) · [Configuration](blink-ai/references/configuration.md) · [Troubleshooting](blink-ai/references/diagnostics.md) · [Feedback](blink-ai/references/feedback.md)

macOS workflows have been tested end to end. Windows binaries have passed architecture and integrity checks; complete Windows Python/R workflow validation remains pending. The distribution includes native binaries without BLINK algorithm C source.

## Citation

If you use BLINK-AI in your research, please cite the following publications:

- [BLINK: a package for the next level of genome-wide association studies with both individuals and markers in the millions](https://doi.org/10.1093/gigascience/giy154).
- [GWAS Procedures for Gene Mapping in Diverse Populations With Complex Structures](https://bio-protocol.org/en/bpdetail?id=5284&type=0).

Bundled GAPIT components retain their original attribution and license; see [third-party notices](THIRD_PARTY_NOTICES.md).
