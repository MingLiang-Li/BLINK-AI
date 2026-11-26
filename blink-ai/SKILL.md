---
name: blink-ai
description: Run and interpret genome-wide association studies with BLINK_c. Convert and merge genotype datasets, check sample alignment and quality, diagnose failures, and use the bundled GAPIT functions for phenotype simulation and plotting.
---

# BLINK-AI

Use this skill in a host that can run local Python, R, and native programs. See [installation](INSTALL.md) for supported platforms and prerequisites.

For first use, read the [usage guide](references/usage.md). The default `demo` analyzes the bundled [rice dataset](references/example-data.md): six VCF.gz chunks, one measured trait, and four supplied PCs. `demo --simulation` uses a separate small genotype fixture.

## Analysis workflow

1. Read the entire [GWAS R template](assets/templates/BLINK_AI_GWAS_template.R) before preparing an analysis. Adapt the JSON configuration and retain the template's input checks, native GWAS, result validation, and reporting steps.
2. Identify the genotype format, sample IDs, target traits, covariates, and analysis scope. Use a measured phenotype for real-data GWAS. Enable simulation only when explicitly requested.
3. Prepare the R environment with `setup-environment`, then inspect it. The standard run also prepares the project R library automatically and installs missing dependencies. If Rscript is absent, install R for the user's platform and rerun setup. Use [configuration](references/configuration.md), [engine parameters](references/parameters.md), and [genotype formats](references/format-conversion.md) to resolve format, sample alignment, quality control, missingness, and any information loss.
4. Run the template through the CLI in a new output directory. Merge genotype chunks before a genome-wide scan so they share one conditional model.
5. Verify that the run manifest reports `completed` and that the expected marker tables, plots, and report exist. Interpret corrected results using [genetics](references/genetics.md). Use [troubleshooting](references/diagnostics.md) to investigate failed stages.

Always generate Manhattan and QQ plots by calling the bundled `GAPIT.Manhattan` and `GAPIT.QQ` functions through the standard R template. The default styles are `Oceanic` and `rainbow`. Preserve the template's plot validation and `results/plotting.json` record.

## User feedback

When the user reports a problem, error, suggestion, or code change request, create a local report using [feedback reporting](references/feedback.md). Set the project root explicitly. Preserve the user's original wording and attach the relevant run. If that run already has an automatic feedback ID, update that record with the user context and handling history.

User requirements and user experience are required sections. Keep an unevaluated experience explicitly marked as such. Record code changes by function, location, reason, and before/after behavior. Associate verification claims with existing evidence files and record the applicable versions. Promote confirmed fixes to local regression cases with reproduction steps and acceptance criteria. Keep untested checks pending. Leave user acceptance for the user to report.

## Commands

Replace `SKILL_DIR` with this directory. On Windows, use `python` or `py -3` in place of `python3`.

```bash
python3 "SKILL_DIR/scripts/blinkc_runner.py" setup-environment --project-root .
python3 "SKILL_DIR/scripts/blinkc_runner.py" inspect-environment --profile gwas
python3 "SKILL_DIR/scripts/blinkc_runner.py" demo --output-dir demo-gwas
python3 "SKILL_DIR/scripts/blinkc_runner.py" init-config --output analysis.json
python3 "SKILL_DIR/scripts/blinkc_runner.py" run --config analysis.json
python3 "SKILL_DIR/scripts/blinkc_runner.py" parameters
python3 "SKILL_DIR/scripts/blinkc_runner.py" search-knowledge "QQ plot"
```

Add `--simulation` to the demo command for the simulated phenotype example. To convert genotype data, provide the source format, target format, input file or prefix, and a new output directory.

```bash
python3 "SKILL_DIR/scripts/blinkc_runner.py" convert --from vcf --to plink --input genotypes.vcf --output-dir converted
```

Keep the metadata sidecars with converted files. When known allele labels are unavailable, obtain the metadata or use synthetic labels with the user's explicit permission.

## References

- [BLINK_c input and output contract](references/engine-contract.md)
- [Evaluation scenarios](evals/README.md)
- [Feedback reporting and issue tracking](references/feedback.md)
- [Conversion performance and resource use](references/performance.md)
