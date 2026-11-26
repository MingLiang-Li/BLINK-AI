"""Validated BLINK_c format conversion through legacy bit planes.

Python handles metadata, preflight, genotype checksums and process control.
Native BLINK_c imports hardcalls; blinkc-export writes target genotypes in C.
"""
import csv
from functools import lru_cache
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.parse import quote

import blinkc_runner as runner

FORMATS = ("plink", "vcf", "vcf_gz", "numeric", "hapmap", "blink")
SUFFIXES = {"plink": (".bed", ".bim", ".fam"), "vcf": (".vcf",), "vcf_gz": (".vcf.gz",),
            "numeric": (".dat", ".map"), "hapmap": (".hmp",),
            "blink": (".pre", ".pos", ".val", ".map")}
SAMPLE_HEADER = ["sample_id", "fid", "iid", "father", "mother", "sex", "phenotype"]
VARIANT_HEADER = ["snp_id", "chromosome", "position", "ref", "alt", "cm"]
IUPAC = {"A": "AA", "C": "CC", "G": "GG", "T": "TT", "R": "AG", "Y": "CT", "S": "CG",
         "W": "AT", "K": "GT", "M": "AC"}


# Byte lookups keep hard-call decoding in bulk operations while preserving
# the canonical marker-major SHA-256 used by existing conversion sidecars.
GT_CODES = {
    left + separator + right: 3 if "." in (left, right) else int(left) + int(right)
    for left in ("0", "1", ".") for right in ("0", "1", ".") for separator in ("/", "|")
}
GT_CODES["."] = 3
PHASED_GT = {gt for gt in GT_CODES if "|" in gt}
PARTIAL_GT = {gt for gt in GT_CODES if "." in gt and gt not in (".", "./.", ".|.")}
BED_CODES = tuple(bytes((2, 3, 1, 0)[(byte >> (2 * shift)) & 3] for shift in range(4)) for byte in range(256))
NUMERIC_CODES = bytes.maketrans(b"0123", bytes(range(4)))
VAL_WEIGHTS = bytes.maketrans(bytes(range(4)), bytes((0, 1, 4, 5)))
BIT_PLANE_CODES = None


def bit_plane_codes():
    global BIT_PLANE_CODES
    if BIT_PLANE_CODES is None:
        BIT_PLANE_CODES = tuple(bytes((((high >> shift) & 1) << 1) | ((low >> shift) & 1)
                                     for shift in range(7, -1, -1))
                                for high in range(256) for low in range(256))
    return BIT_PLANE_CODES


def ext(prefix, suffix):
    return Path(str(prefix) + suffix)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text_open(path):
    return gzip.open(path, "rt", encoding="utf-8") if str(path).endswith(".gz") else Path(path).open(encoding="utf-8")


def read_tsv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path, header, records):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows([[record[key] for key in header] for record in records])


def samples_from_ids(ids):
    return [dict(zip(SAMPLE_HEADER, (value, value, value, "0", "0", "0", "-9"))) for value in ids]


def load_samples(path):
    result = read_tsv(path)
    require(result and "sample_id" in result[0], "Samples TSV needs sample_id header")
    defaults = samples_from_ids([row["sample_id"] for row in result])
    for default, row in zip(defaults, result):
        default.update({key: row[key] for key in SAMPLE_HEADER if key in row})
    return defaults


def variant(marker, chromosome, position, ref, alt, cm="0"):
    return dict(zip(VARIANT_HEADER, (marker, chromosome, str(position), ref, alt, str(cm))))


def map_variants(prefix):
    with ext(prefix, ".map").open(encoding="utf-8") as handle:
        rows = [line.split() for line in handle if line.strip()]
    require(rows, "Empty map")
    if rows[0][0].lower() in ("rs", "snp", "snp_id", "rs#"):
        rows = rows[1:]
    require(all(len(row) == 3 for row in rows), "Numeric/BLINK .map must have three columns: SNP chromosome position")
    return [variant(row[0], row[1], row[2], "", "") for row in rows]


def validate_metadata(samples, variants):
    require(samples and variants, "At least one sample and marker are required")
    for records, field in ((samples, "sample_id"), (variants, "snp_id")):
        ids = [record[field] for record in records]
        require(len(ids) == len(set(ids)), "Duplicate " + field)
    for sample in samples:
        for key in SAMPLE_HEADER:
            value = sample[key]
            require(isinstance(value, str) and value and not re.search(r"\s", value), "Empty/whitespace sample field: " + key)
            require(len(value.encode("utf-8")) <= 80, "Sample field too long for legacy BLINK_c")
    for row in variants:
        require(row["snp_id"] not in ("", ".") and not re.search(r"\s", row["snp_id"]), "Invalid marker ID")
        require(len(row["snp_id"].encode("utf-8")) <= 80, "Marker ID too long for legacy BLINK_c")
        require(row["chromosome"] and not re.search(r"\s", row["chromosome"]), "Invalid chromosome")
        require(len(row["chromosome"].encode("utf-8")) <= 80, "Chromosome label too long for legacy BLINK_c")
        require(0 < int(row["position"]) <= 2147483646, "Position outside supported 32-bit BLINK_c range")
        require(row["ref"] in "ACGT" and len(row["ref"]) == 1 and row["alt"] in "ACGT"
                and len(row["alt"]) == 1 and row["ref"] != row["alt"], "Only biallelic A/C/G/T SNPs are supported")
        require(len(row["cm"]) <= 30 and not re.search(r"\s", row["cm"]), "Invalid genetic distance")
        require(math.isfinite(float(row["cm"])), "Genetic distance must be finite")


def hapmap_code(value, ref, alt):
    if value in ("N", "NN", ".", "..", "?"):
        return 3
    value = IUPAC.get(value, value)
    require(len(value) == 2 and all(base in (ref, alt) for base in value), "HapMap genotype does not match declared alleles")
    return value.count(alt)


@lru_cache(maxsize=12)
def hapmap_codes(ref, alt):
    codes = {"N": 3, "NN": 3, ".": 3, "..": 3, "?": 3,
             ref * 2: 0, ref + alt: 1, alt + ref: 1, alt * 2: 2}
    for letter, bases in IUPAC.items():
        if all(base in (ref, alt) for base in bases):
            codes[letter] = bases.count(alt)
    return codes


def scan_vcf(path, allow_lossy):
    samples, variants, losses = [], [], set()
    digest = hashlib.sha256()
    with text_open(path) as handle:
        for line in handle:
            if line.startswith("##"):
                continue
            columns = line.rstrip("\r\n").split("\t")
            if line.startswith("#CHROM\t"):
                require(not samples, "Duplicate VCF sample header")
                samples = samples_from_ids(columns[9:])
                continue
            require(samples and len(columns) == 9 + len(samples), "Malformed VCF or missing sample header")
            chrom, pos, marker, ref, alt, quality, filt, info, format_text = columns[:9]
            require(len(ref) == len(alt) == 1 and ref in "ACGT" and alt in "ACGT" and ref != alt,
                    "Only diploid biallelic SNP VCF hardcalls supported; split/normalize other variants first")
            if marker == ".":
                marker = ":".join((chrom, pos, ref, alt))
                losses.add("Missing VCF IDs replaced by CHROM:POS:REF:ALT")
            variants.append(variant(marker, chrom, pos, ref, alt))
            keys = format_text.split(":")
            require("GT" in keys, "VCF has no GT hardcall field")
            if keys != ["GT"]:
                losses.add("Per-sample FORMAT fields other than GT are omitted")
            if quality != "." or filt != "." or info != ".":
                losses.add("VCF QUAL/FILTER/INFO annotations are omitted")
            gt_index = keys.index("GT")
            fields = columns[9:]
            if keys == ["GT"]:
                genotypes = fields
            else:
                try:
                    genotypes = [value.split(":")[gt_index] for value in fields]
                except IndexError as error:
                    raise ValueError("Missing VCF GT field") from error
            present = set(genotypes)
            require(present <= GT_CODES.keys(), "Only diploid 0/1 GT values or missing calls supported")
            if present & PHASED_GT:
                losses.add("Genotype phasing is discarded")
            if present & PARTIAL_GT:
                losses.add("Partially missing GT becomes a fully missing hardcall")
            digest.update(bytes(map(GT_CODES.__getitem__, genotypes)))
    substantive = losses - {"Missing VCF IDs replaced by CHROM:POS:REF:ALT"}
    require(allow_lossy or not substantive, "Conversion would lose information; use --allow-lossy explicitly: " + "; ".join(sorted(substantive)))
    return samples, variants, digest.hexdigest(), sorted(losses)


def scan_plink(prefix):
    fam = [line.split() for line in ext(prefix, ".fam").read_text(encoding="utf-8").splitlines() if line.strip()]
    require(fam and all(len(row) == 6 for row in fam), "PLINK .fam needs six columns, without a header")
    iid_unique = len({row[1] for row in fam}) == len(fam)
    samples = [dict(zip(SAMPLE_HEADER, ((row[1] if iid_unique else quote(row[0], safe="") + "/" + quote(row[1], safe="")), *row))) for row in fam]
    require(len({(row[0], row[1]) for row in fam}) == len(fam), "Duplicate PLINK FID/IID")
    bim = [line.split() for line in ext(prefix, ".bim").read_text(encoding="utf-8").splitlines() if line.strip()]
    require(bim and all(len(row) == 6 for row in bim), "PLINK .bim needs six columns")
    # Existing BLINK_c counts A1. Canonical ALT is A1, encoding REF is A2.
    variants = [variant(row[1], row[0], row[3], row[5], row[4], row[2]) for row in bim]
    digest = hashlib.sha256()
    size = (len(samples) + 3) // 4
    with ext(prefix, ".bed").open("rb") as handle:
        require(handle.read(3) == b"\x6c\x1b\x01", "Only SNP-major PLINK BED supported")
        for _ in variants:
            block = handle.read(size)
            require(len(block) == size, "Truncated PLINK BED")
            digest.update(b"".join(map(BED_CODES.__getitem__, block))[:len(samples)])
        require(not handle.read(1), "Unexpected trailing PLINK BED bytes")
    return samples, variants, digest.hexdigest(), []


def scan_hapmap(path, allow_lossy=False):
    digest = hashlib.sha256()
    variants = []
    losses = set()
    with Path(path).open(encoding="utf-8") as handle:
        header = handle.readline().rstrip("\r\n").split("\t")
        require(len(header) >= 12, "HapMap requires 11 metadata columns and sample columns")
        samples = samples_from_ids(header[11:])
        for line in handle:
            row = line.rstrip("\r\n").split("\t")
            require(len(row) == len(header) and len(row[1]) == 3 and row[1][1] == "/", "Malformed biallelic HapMap row")
            require(row[4] in ("+", "NA", "."), "Minus-strand HapMap must be normalized before conversion")
            if any(value not in ("NA", ".", "0") for value in row[5:11]):
                losses.add("HapMap assembly/annotation fields are omitted")
            variants.append(variant(row[0], row[2], row[3], row[1][0], row[1][2]))
            codes = hapmap_codes(row[1][0], row[1][2])
            try:
                digest.update(bytes(map(codes.__getitem__, row[11:])))
            except KeyError as error:
                raise ValueError("HapMap genotype does not match declared alleles") from error
    require(allow_lossy or not losses, "Conversion would lose HapMap annotations; use --allow-lossy explicitly")
    return samples, variants, digest.hexdigest(), sorted(losses)


def legacy_blink_metadata(prefix):
    path = ext(prefix, ".inf")
    if not path.exists():
        return None, None
    with path.open(encoding="utf-8") as handle:
        line = handle.readline().strip()
        match = re.match(r"(vcf|hapmap|plink|numeric):(\d+):(\d+)", line)
        require(match is not None, "Unrecognized legacy BLINK .inf; supply metadata sidecars")
        family, m, n = match.group(1), int(match.group(2)), int(match.group(3))
        if family == "numeric":
            return None, None
        if family == "vcf":
            for line in handle:
                if line.startswith("#CHROM\t"):
                    ids = line.rstrip().split("\t")[9:]
                    break
            else:
                raise ValueError("No sample header in BLINK VCF .inf")
            variants = []
            for line in handle:
                row = line.split()
                require(len(row) >= 5, "Malformed BLINK .inf variant")
                variants.append(variant(row[2], row[0], row[1], row[3], row[4]))
        elif family == "hapmap":
            ids = handle.readline().split()[11:]
            variants = []
            for line in handle:
                row = line.split()
                require(len(row) >= 11, "Malformed BLINK HapMap .inf")
                variants.append(variant(row[0], row[2], row[3], row[1][0], row[1][2]))
        else:
            ids = handle.readline().split()
            variants = []
            for line in handle:
                row = line.split()
                require(len(row) == 6, "Malformed BLINK PLINK .inf")
                variants.append(variant(row[1], row[0], row[3], row[5], row[4], row[2]))
        require(len(ids) == n and len(variants) == m, "BLINK .inf counts differ from metadata")
    return samples_from_ids(ids), variants


def blink_digest(prefix, n, m):
    digest = hashlib.sha256()
    words = (n + 63) // 64
    lookup = bit_plane_codes()
    residue = n % 64
    full_samples = n - residue
    with ext(prefix, ".pre").open("rb") as high, ext(prefix, ".pos").open("rb") as low, ext(prefix, ".val").open("rb") as values:
        for _ in range(m):
            a, b = high.read(words * 8), low.read(words * 8)
            require(len(a) == len(b) == words * 8, "Truncated BLINK binary")
            # Words are little endian. Samples run from the high bit to the
            # low bit, with a short final word aligned to its low bits.
            high_bytes = b"".join(a[offset:offset+8][::-1] for offset in range(0, len(a), 8))
            low_bytes = b"".join(b[offset:offset+8][::-1] for offset in range(0, len(b), 8))
            expanded = b"".join(lookup[(hi << 8) | lo] for hi, lo in zip(high_bytes, low_bytes))
            codes = expanded[:full_samples] + expanded[-residue:] if residue else expanded
            digest.update(codes)
            raw = values.read(4)
            require(len(raw) == 4 and int.from_bytes(raw, "little") == sum(codes.translate(VAL_WEIGHTS)),
                    "BLINK .val checksum differs from genotype bit planes")
        require(high.read() in (b"", b"\x03\0\0\0") and low.read() in (b"", b"\x03\0\0\0"), "Unknown BLINK trailing mask")
    require(ext(prefix, ".val").stat().st_size == m * 4, "Invalid BLINK .val size")
    return digest.hexdigest()


def inspect_input(prefix, format_name, samples_path=None, alleles_path=None, allow_synthetic=False, allow_lossy=False):
    require(format_name in FORMATS, "Unknown input format")
    requested = Path(prefix).resolve()
    prefix = requested
    if requested.is_file():
        suffixes = (".hmp.txt", ".hmp") if format_name == "hapmap" else SUFFIXES[format_name]
        for suffix in suffixes:
            if str(requested).endswith(suffix):
                prefix = Path(str(requested)[:-len(suffix)])
                break
    files = {suffix: ext(prefix, suffix) for suffix in SUFFIXES[format_name]}
    if format_name == "hapmap":
        if requested.is_file() and str(requested).endswith((".hmp", ".hmp.txt")):
            files[".hmp"] = requested
        elif not files[".hmp"].exists() and ext(prefix, ".hmp.txt").is_file():
            files[".hmp"] = ext(prefix, ".hmp.txt")
    for suffix in SUFFIXES[format_name]:
        require(files[suffix].is_file(), "Missing companion file: " + str(files[suffix]))
    samples_sidecar = Path(samples_path) if samples_path else ext(prefix, ".samples.tsv")
    variants_sidecar = Path(alleles_path) if alleles_path else ext(prefix, ".variants.tsv")
    losses = []
    if format_name in ("vcf", "vcf_gz"):
        samples, variants, signature, losses = scan_vcf(ext(prefix, SUFFIXES[format_name][0]), allow_lossy)
    elif format_name == "plink":
        samples, variants, signature, losses = scan_plink(prefix)
    elif format_name == "hapmap":
        samples, variants, signature, losses = scan_hapmap(files[".hmp"], allow_lossy)
    else:
        samples, variants = legacy_blink_metadata(prefix) if format_name == "blink" else (None, None)
        variants = variants or map_variants(prefix)
        if samples is None:
            require(samples_sidecar.is_file(), "Numeric/BLINK sample identity is unknown; provide --samples TSV with sample_id")
            samples = load_samples(samples_sidecar)
        if format_name == "numeric":
            digest = hashlib.sha256()
            count = 0
            with ext(prefix, ".dat").open(encoding="ascii") as handle:
                for line in handle:
                    values = line.split()
                    require(len(values) == len(samples) and set(values) <= {"0", "1", "2", "3"},
                            "Numeric .dat must be marker x sample hardcalls 0/1/2, missing=3")
                    digest.update("".join(values).encode("ascii").translate(NUMERIC_CODES))
                    count += 1
            require(count == len(variants), "Numeric marker count differs from .map")
            signature = digest.hexdigest()
        else:
            signature = blink_digest(prefix, len(samples), len(variants))
    if samples_sidecar.is_file():
        provided = load_samples(samples_sidecar)
        if format_name != "plink":
            require([x["sample_id"] for x in provided] == [x["sample_id"] for x in samples], "Samples sidecar order/IDs differ from input")
        if format_name == "plink":
            require([(x["fid"], x["iid"]) for x in provided] == [(x["fid"], x["iid"]) for x in samples], "Samples sidecar FID/IID differs from .fam")
        samples = provided
    if variants_sidecar.is_file():
        provided = read_tsv(variants_sidecar)
        require(len(provided) == len(variants), "Variants sidecar count differs")
        for row, original in zip(provided, variants):
            require(all(row[key] == original[key] for key in ("snp_id", "chromosome", "position")), "Variants sidecar order/coordinates differ")
            if original["ref"]:
                require((row["ref"], row["alt"]) == (original["ref"], original["alt"]), "Variants sidecar allele orientation differs")
            original.update({key: row[key] for key in VARIANT_HEADER if key in row})
    synthetic = any(not row["ref"] or not row["alt"] for row in variants)
    if synthetic:
        require(allow_synthetic, "Allele identities unavailable; provide --alleles TSV or explicitly --allow-synthetic-alleles")
        for row in variants:
            if not row["ref"] or not row["alt"]:
                row.update(ref="A", alt="T")
        losses.append("Synthetic A/T encoding labels: not biological reference/alternate alleles")
    metadata_path = ext(prefix, ".conversion-meta.json")
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        require(metadata.get("schema_version") == "1" and metadata["genotype_sha256"] == signature,
                "Conversion provenance does not match genotype hardcalls")
        require(runner.sha256_file(samples_sidecar) == metadata["samples_sha256"]
                and runner.sha256_file(variants_sidecar) == metadata["variants_sha256"], "Conversion provenance does not match metadata sidecars")
        synthetic = synthetic or metadata["synthetic_alleles"]
        losses = sorted(set(losses + metadata["information_changes"]))
    validate_metadata(samples, variants)
    return {"prefix": str(prefix), "files": files, "format": format_name, "samples": samples, "variants": variants,
            "genotype_sha256": signature, "information_changes": losses, "synthetic_alleles": synthetic}


def execute(argv, work, label, commands):
    started = time.perf_counter()
    record = {"argv": list(map(str, argv)), "cwd": str(work), "started_at": runner.utc_now()}
    commands.append(record)
    with (work / (label + ".stdout.log")).open("wb") as out, (work / (label + ".stderr.log")).open("wb") as err:
        try:
            process = subprocess.run(record["argv"], cwd=work, stdout=out, stderr=err, timeout=3600, check=False)
        except subprocess.TimeoutExpired:
            record.update(status="timeout", finished_at=runner.utc_now(), duration_seconds=time.perf_counter() - started)
            raise ValueError("Conversion subprocess timed out; see " + label + ".stderr.log")
    record.update(returncode=process.returncode, finished_at=runner.utc_now(), duration_seconds=time.perf_counter() - started)
    require(process.returncode == 0, "Native conversion failed; see " + label + ".stderr.log")


def canonical_inf(prefix, samples, variants):
    with ext(prefix, ".inf").open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("vcf:%d:%d\n##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t" % (len(variants), len(samples)))
        handle.write("\t".join(s["sample_id"] for s in samples) + "\n")
        for row in variants:
            handle.write("\t".join((row["chromosome"], row["position"], row["snp_id"], row["ref"], row["alt"], ".", ".", ".", "GT")) + "\n")


def convert(input_prefix, input_format, output_format, output_dir, samples_path=None, alleles_path=None,
            allow_synthetic=False, allow_lossy=False):
    started = time.perf_counter()
    phase_started = started
    timings = {}

    def checkpoint(name):
        nonlocal phase_started
        now = time.perf_counter()
        timings[name] = now - phase_started
        phase_started = now

    require(output_format in FORMATS, "Unknown output format")
    environment = runner.inspect_environment()
    require(environment["ready"], "Native BLINK_c prerequisites unavailable")
    manifest = runner.load_manifest()
    tools = [x for x in manifest.get("conversion_tools", []) if x["system"] == environment["host"]["system"]
             and x["architecture"] == environment["host"]["architecture"]]
    require(len(tools) == 1, "The native conversion executable is unavailable for this platform")
    native = runner.bundled_path(runner.SKILL_ROOT, tools[0]["path"])
    require(runner.sha256_file(native) == tools[0]["sha256"], "Native converter hash mismatch")
    data = inspect_input(input_prefix, input_format, samples_path, alleles_path, allow_synthetic, allow_lossy)
    checkpoint("environment_and_input_validation")
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    work = root / "work"
    work.mkdir()
    (root / "output").mkdir()
    report = {"schema_version": "1", "tool_version": runner.VERSION, "status": "running", "started_at": runner.utc_now(),
              "input_format": input_format, "output_format": output_format, "input_prefix": data["prefix"],
              "output_prefix": str(root / "output/data"), "sample_count": len(data["samples"]), "marker_count": len(data["variants"]),
              "genotype_sha256": data["genotype_sha256"], "information_changes": data["information_changes"],
              "synthetic_alleles": data["synthetic_alleles"], "engine_sha256": environment["engine"]["actual_sha256"],
              "converter_sha256": tools[0]["sha256"], "commands": [],
              "performance": {"execution_model": "sequential_stages", "validation": "all_hardcalls",
                              "timings_seconds": timings}}
    source_files = list(data["files"].values())
    source_files += [Path(samples_path) if samples_path else ext(data["prefix"], ".samples.tsv"),
                     Path(alleles_path) if alleles_path else ext(data["prefix"], ".variants.tsv"),
                     ext(data["prefix"], ".conversion-meta.json")]
    if input_format == "blink":
        source_files.append(ext(data["prefix"], ".inf"))
    report["input_files"] = {str(path.resolve()): runner.sha256_file(path) for path in source_files if path.is_file()}
    checkpoint("input_file_hashes")
    runner.write_json(root / "conversion.json", report)
    try:
        prefix = Path(data["prefix"])
        staged = work / "input"
        for suffix in SUFFIXES[input_format]:
            shutil.copyfile(data["files"][suffix], ext(staged, suffix))
        import_prefix = staged
        if input_format in ("vcf", "vcf_gz"):
            execute([native, "--normalize-vcf", ext(staged, SUFFIXES[input_format][0]), work / "normalized.vcf"],
                    work, "normalize_vcf", report["commands"])
            import_prefix = work / "normalized"
        if input_format == "numeric":
            with ext(prefix, ".dat").open(encoding="ascii") as source, ext(staged, ".dat").open("w", encoding="ascii", newline="\n") as target:
                for line in source:
                    target.write(" ".join(line.split()) + "\n")
        if input_format == "hapmap":
            execute([native, "--normalize-hapmap", ext(staged, ".hmp"), work / "normalized.hmp"], work, "normalize_hapmap", report["commands"])
            shutil.copyfile(work / "normalized.hmp", ext(staged, ".hmp"))
        hub = work / "hub"
        if input_format == "blink":
            for suffix in SUFFIXES["blink"]:
                shutil.copyfile(ext(staged, suffix), ext(hub, suffix))
        else:
            flags = {"plink": ["--plink"], "vcf": ["--vcf", "--uvcf"], "vcf_gz": ["--vcf", "--zvcf"],
                     "numeric": ["--numeric"], "hapmap": ["--hapmap"]}[input_format]
            if input_format in ("vcf", "vcf_gz"):
                flags = ["--vcf", "--uvcf"]
            execute([environment["engine"]["resolved_path"], "--file", import_prefix, "--out", hub, *flags, "--compress", "--noimp"], work, "import", report["commands"])
        checkpoint("staging_and_native_import")
        ns, nm = len(data["samples"]), len(data["variants"])
        require(blink_digest(hub, ns, nm) == data["genotype_sha256"], "BLINK_c import changed hardcalls; conversion rejected")
        checkpoint("import_hardcall_validation")
        write_tsv(ext(hub, ".samples.tsv"), SAMPLE_HEADER, data["samples"])
        write_tsv(ext(hub, ".variants.tsv"), VARIANT_HEADER, data["variants"])
        # Metadata normalization is independent of genotype bit planes.
        with ext(hub, ".map").open("w", encoding="utf-8", newline="\n") as handle:
            handle.write("rs\tchr\tpos\n")
            for row in data["variants"]:
                handle.write("\t".join((row["snp_id"], row["chromosome"], row["position"])) + "\n")
        canonical_inf(hub, data["samples"], data["variants"])
        checkpoint("hub_metadata")
        output = root / "output/data"
        if output_format == "blink":
            for suffix in (*SUFFIXES["blink"], ".inf"):
                shutil.copyfile(ext(hub, suffix), ext(output, suffix))
        else:
            execute([native, hub, ext(hub, ".samples.tsv"), ext(hub, ".variants.tsv"), output_format, output, str(nm)], work, "export", report["commands"])
        checkpoint("native_export")
        write_tsv(ext(output, ".samples.tsv"), SAMPLE_HEADER, data["samples"])
        write_tsv(ext(output, ".variants.tsv"), VARIANT_HEADER, data["variants"])
        runner.write_json(ext(output, ".conversion-meta.json"), {
            "schema_version": "1", "genotype_sha256": data["genotype_sha256"],
            "samples_sha256": runner.sha256_file(ext(output, ".samples.tsv")),
            "variants_sha256": runner.sha256_file(ext(output, ".variants.tsv")),
            "synthetic_alleles": data["synthetic_alleles"], "information_changes": data["information_changes"],
            "reference_status": "Encoding orientation; genomic reference not independently verified",
        })
        checked = inspect_input(output, output_format)
        require(checked["genotype_sha256"] == data["genotype_sha256"], "Output hardcalls differ from input")
        require(checked["samples"] == data["samples"] and checked["variants"] == data["variants"], "Output metadata differ from input")
        checkpoint("output_metadata_and_hardcall_validation")
        report.update(status="completed", output_files={p.name: runner.sha256_file(p) for p in sorted((root / "output").iterdir())},
                      hardcalls_verified=True, metadata_verified=True)
        checkpoint("output_file_hashes")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        report["finished_at"] = runner.utc_now()
        report["performance"]["total_seconds"] = time.perf_counter() - started
        runner.write_json(root / "conversion.json", report)
    return report
