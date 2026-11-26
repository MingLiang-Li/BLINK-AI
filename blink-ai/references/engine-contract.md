# BLINK_c input and output contract

- BLINK Numeric uses a headerless SNP-by-sample matrix with space-delimited hard calls 0, 1, and 2. Code 3 represents a missing call. The map identifies SNP ID, chromosome, and position.
- Native phenotype and covariate tables have a `taxa` column followed by numeric fields. BLINK_c consumes them in genotype sample order. The skill aligns by sample ID before invoking BLINK_c.
- BLINK-AI merges genotype chunks in numeric order before performing genome-wide GWAS. Input labels are preserved in the reported traits and coordinates.
- The native GWAS table has columns `taxa`, `chr`, `pos`, `maf`, and `p_value`. Here `taxa` identifies the SNP. The result validator checks unique SNPs, coordinates, order, and finite P values and MAF within range. It preserves exact zero P values.
- `--cycle_size` starts at 2,000 SNPs by default. On a block workspace failure, BLINK_c resumes with smaller blocks. Exit code 20 indicates an unrecoverable allocation failure.

See [configuration](configuration.md) for result files and [parameters](parameters.md) for available options.
