# Troubleshoot an analysis

Start with the failed stage in `manifest.json`, its logged command, and stderr. Use a new output directory after correcting the cause.

| Symptom | What to check |
|---|---|
| Executable fails to start | Run `inspect-environment --profile gwas`. Check the OS, CPU architecture, executable permissions, and reported hash. |
| R stage fails | Check Rscript discovery, `jsonlite`, and the R log. Confirm that the plotting and reporting stages completed. |
| Dependency setup fails | Inspect `r-environment.json` and `r-setup.stderr.log`. Check the CRAN connection and project library permissions, then rerun `setup-environment`. |
| Tables have the same number of rows but disagree | Compare unique sample IDs and order, including PLINK FID and IID. Align by sample ID. |
| Sample count differs by trait | Check the missing phenotype policy and the covariate rows for the observed subset. The value `-9` is numeric. |
| Numeric import fails | Check SNP-by-sample orientation, hard calls 0/1/2/3, the map, and sample metadata. Continuous dosages need an explicit hard-calling procedure. |
| VCF has multiple FORMAT fields | Identify GT and check ploidy and alleles. Conversion requires consent before dropping phase or annotations. |
| Merge has fewer markers than expected | Check numbered chunk prefixes, duplicate SNP IDs, QC exclusions, and sample order. Verify the complete genome-wide marker set. |
| Process exits with code 0 but results are missing | Verify the expected files and the complete SNP set, order, coordinates, P values, and MAF. Record the run as failed if required results are absent. |
| Invalid P values or MAF | Check constant markers, genotype encoding, missing calls, sample alignment, and model rank. |
| Plot reports `non-finite ylim` | Check that validated P values exist and use numeric input. Exact zero P values are retained in results and bounded for plotting. |
| QQ plot shows inflation or deflation | Review population structure, relatedness, batches, duplicate samples, coding, sample size, and model fit. |
| Covariate fit fails | Check constants and collinearity with the intercept in the observed sample subset for each trait. |
| No SNP passes correction | Report the result and review sample size, model design, QC, and correction. Keep the prespecified threshold. |
| `GWAS cycle_size reduced` appears | BLINK_c resumed the current SNP with a smaller block. The log gives the iteration and SNP number. |
| BLINK_c exits with code 20 | Check the native log for the allocation that failed. The minimum GWAS block is one SNP. Model workspace and other stages have independent memory requirements. |
| Process is terminated or times out | Identify the stage and inspect system and application logs for memory, disk, and time limits. |

The analysis manifest links automatically recorded failure feedback. Use that feedback ID to add the user's request and experience, handling steps, code changes, and verification evidence. Follow [feedback reporting](feedback.md) for state tracking and local regression cases.
