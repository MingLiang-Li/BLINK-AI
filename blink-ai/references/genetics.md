# Interpret a GWAS

BLINK uses a fixed-effects scan and iteratively selects marker covariates using linkage disequilibrium (LD) and the Bayesian information criterion (BIC). See the [BLINK paper](https://academic.oup.com/gigascience/article/8/2/giy154/5238723).

Use covariates supported by the study design. Check the rank of the model including its intercept for the observed sample subset of each trait. Principal components can be supplied as fixed covariates. This workflow fits quantitative-trait BLINK or GLM models. Use a model suited to the study for kinship, genomic prediction, or logistic case-control analysis.

MAF is the frequency of the less common allele. The genotype codes 0, 1, and 2 count copies of the encoded ALT allele. A synthetic allele label carries no biological identity. Choose MAF and missingness thresholds in light of the sample size and study design.

For a trait with `M` retained tests, the Bonferroni threshold is `alpha / M`. The workflow uses R's `p.adjust` for Bonferroni and Benjamini–Hochberg (BH) correction. Correction is per trait and includes all tests, regardless of plotting subsampling. Report the method and its error-rate interpretation.

The genomic inflation factor is the median of the observed 1-df chi-squared statistics divided by the median of the 1-df chi-squared distribution. Examine deviations alongside structure, relatedness, batches, technical artifacts, and possible polygenic signal. The reported P values receive no genomic-control adjustment. Exact zero P values are retained in tables and bounded only for plotting.

A cluster of associated SNPs may tag one LD region. Use the genome assembly, annotations, LD, and fine-mapping evidence to discuss candidate genes. BLINK_c returns P values and MAF, so effect size, direction, standard error, effect allele, and variance explained require separate estimates.

For simulated data, compare discoveries with causal SNPs by ID. Power is the proportion of simulated causal SNPs discovered. The false discovery proportion (FDP) is the proportion of discoveries outside that set, defined as zero with no discoveries. Estimating expected power or FDR requires repeated simulations under a specified design.
