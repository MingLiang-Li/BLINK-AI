# Rice example dataset

The default `demo` uses a measured rice phenotype, six genotype chunks, and four supplied covariates. Data are bundled under [`assets/examples/rice/`](../assets/examples/rice/); the [configuration](../assets/examples/gwas.example.json) selects the trait, covariates, and QC settings.

## Contents

| File | Contents |
|---|---|
| `genotypes/001_rice_chr01a.vcf.gz` | Chromosome 1, part A; 2,717 SNPs |
| `genotypes/002_rice_chr01b.vcf.gz` | Chromosome 1, part B; 3,748 SNPs |
| `genotypes/003_rice_chr02.vcf.gz` | Chromosome 2; 3,872 SNPs |
| `genotypes/004_rice_chr03.vcf.gz` | Chromosome 3; 4,361 SNPs |
| `genotypes/005_rice_chr04-07.vcf.gz` | Chromosomes 4–7; 11,047 SNPs |
| `genotypes/006_rice_chr08-12.vcf.gz` | Chromosomes 8–12; 11,156 SNPs |
| `phenotypes.tsv` | 413 unique IDs; `Faridpur_Aberdeen_phe` with 304 observed and 109 missing values |
| `covariates.tsv` | The same 413 IDs; complete `PC1`, `PC2`, `PC3`, and `PC4` columns |
| `samples.tsv` | Sample IDs and supplied population labels; informational metadata |
| `dataset.json` | Dimensions, preparation notes, and file SHA-256 hashes |

There are **413 samples, 36,901 SNPs, and 12 chromosomes** before QC. Numeric sample IDs are retained across files. Population labels in `samples.tsv` are not used as model covariates by the example.

## Preparation

The dataset was supplied for this example. Filenames and table ID headers were standardized. The original split-file headers contained repeated population labels; unique sample IDs were recovered from the corresponding reference genotypes and PLINK individual IDs. Comparing every known reference call identifies one unique match for each of the 413 columns. No positional assumption was used in place of this check.

Genotype values, allele labels, marker IDs, coordinates, phenotype values, and covariate values are retained. The supplied chunks already contain complete hard calls, including **660,751 calls that were missing in the reference VCF**. Their earlier filling method was not supplied. The preparation performs no additional imputation; this is a workflow demonstration rather than a reconstruction of raw missingness.

## Run

From the GitHub repository directory:

```bash
python3 blink-ai/scripts/blinkc_runner.py demo --output-dir runs/rice-gwas
```

For an installed skill, replace `blink-ai` with its installed directory. The command resolves bundled input paths automatically. To customize the example directly, edit its JSON in place or update the input paths after copying it elsewhere; paths in a JSON configuration are relative to that file.

## Analysis settings

- Model: BLINK, one genome-wide scan after merging all six chunks.
- Phenotype: `Faridpur_Aberdeen_phe`; exclude its 109 missing observations, leaving 304 analysis samples.
- Covariates: supplied PC1–PC4, included in every model iteration.
- QC: MAF ≥ 0.01, calculated on selected genotype samples before per-trait phenotype exclusion. Genotype missingness is rejected.
- Initial block size: 2,000 SNPs; recoverable block workspace failures use native reduction.
- Reporting: per-trait Bonferroni correction at α = 0.05; BH-adjusted values also saved.
- Plots: bundled `GAPIT.Manhattan` (`Oceanic`) and `GAPIT.QQ` (`rainbow`).

Read `report.html`, then inspect `manifest.json`, `results/summary.json`, and `results/plotting.json` to confirm completion, analysis counts, and plot provenance. Post-QC marker counts and discoveries are analysis outputs, not a guarantee of biological validity.

The macOS ARM64 reference run with the bundled configuration completed with **304 analysis samples, 36,773 tested SNPs, and 4 Bonferroni-significant SNPs**. Its minimum P value was `3.011789e-7`. These values describe this example under the stated settings; use numerical tolerances when comparing platforms. Windows execution of this example remains to be verified.

For phenotype simulation, use `demo --simulation`. That command intentionally uses the separate small fixture under `assets/examples/data/`.
