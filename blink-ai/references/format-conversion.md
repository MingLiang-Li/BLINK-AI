# Genotype format conversion

The `convert` command supports all directions among six representations. Supply the input file or prefix and a new output directory.

| Format | Required files | Representation |
|---|---|---|
| `plink` | `.bed`, `.bim`, `.fam` | PLINK 1 SNP-major binary data |
| `vcf` | `.vcf` | Diploid, biallelic A/C/G/T SNPs with GT hard calls |
| `vcf_gz` | `.vcf.gz` | The same VCF representation in gzip format. Output uses standard gzip. |
| `numeric` | `.dat`, `.map`, and metadata | Headerless SNP-by-sample hard calls. Codes 0, 1, and 2 count ALT copies. Code 3 is missing. |
| `hapmap` | `.hmp` or `.hmp.txt` | HapMap with 11 metadata columns, diploid calls or IUPAC codes, and forward or unknown strand |
| `blink` | `.pre`, `.pos`, `.val`, `.map`, and sample metadata | BLINK binary format. Sample metadata can be read from sidecars or a supported `.inf` file. |

For example, run the following command to convert VCF to PLINK. Replace `SKILL_DIR` with the installed skill directory.

```bash
python3 "SKILL_DIR/scripts/blinkc_runner.py" convert --from vcf --to plink --input genotypes.vcf --output-dir converted
```

The converted files use the prefix `output/data` inside the new directory. `conversion.json` records the inputs, conversions, and output checks.

The report also contains stage timings. See [performance and resource use](performance.md) when choosing storage, input representations, and concurrent independent conversion tasks.

## Sample and variant metadata

Keep the `.samples.tsv`, `.variants.tsv`, and `.conversion-meta.json` sidecars together with the genotype files. These preserve sample identity, allele labels, and the recorded information changes.

For bare Numeric input, provide sample and variant tables with `--samples` and `--alleles` when the metadata cannot be inferred. The sample table needs one unique `sample_id` per row in genotype order. Use the following full header.

```text
sample_id	fid	iid	father	mother	sex	phenotype
```

The variant table uses this header. `cm` is optional and defaults to zero. Match the SNP IDs, coordinates, and order in the map.

```text
snp_id	chromosome	position	ref	alt	cm
```

For PLINK, BIM A1 is the counted ALT label and A2 is the REF label for conversion. These labels describe encoding. Reference-genome REF identity requires independent evidence. Keep BED and BIM in the same orientation.

Numeric data encode counts alone. Provide known alleles where possible. With explicit user consent, `--allow-synthetic-alleles` provides placeholder A/T labels. The sidecar marks them as synthetic. A sample table is still required when sample identities cannot be recovered.

## Information preserved

- Conversion preserves diploid biallelic hard calls, missing calls, sample and variant order, coordinates, and known allele labels.
- GT is located by FORMAT field name. HapMap heterozygotes and IUPAC calls are normalized.
- Phase, other FORMAT fields, nonempty VCF QUAL/FILTER/INFO fields (including `PASS`), and HapMap annotations require explicit `--allow-lossy` before they can be dropped. The conversion report records changes.
- A missing VCF ID becomes `CHROM:POS:REF:ALT`. Duplicate IDs, multiallelic sites, indels, non-diploid calls, and fractional dosages are rejected.
- Use complete sidecars for fields absent from older `.inf` files. Before GWAS, check the separate missingness and QC requirements in [configuration](configuration.md).

Format references are available from [PLINK](https://www.cog-genomics.org/plink/1.9/formats#bed), [VCF](https://samtools.github.io/hts-specs/VCFv4.5.pdf), and [TASSEL](https://tassel.maizegenetics.net/user_manual/load/).
