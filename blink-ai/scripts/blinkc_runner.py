#!/usr/bin/env python3
"""BLINK-AI native engine prerequisites and legacy GWAS result validation.

Python 3.9+, standard library only. Environment inspection never executes BLINK.
"""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys

VERSION = "0.2.8"
SKILL_ROOT = Path(__file__).resolve().parents[1]


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def binary_metadata(path):
    """Read native headers without executing a candidate binary."""
    with Path(path).open("rb") as handle:
        header = handle.read(64)
        if len(header) >= 32 and header[:4] == b"\xcf\xfa\xed\xfe":
            _, cpu, _, filetype, ncmds, size, _, _ = struct.unpack("<8I", header[:32])
            if filetype != 2 or size > 16 * 1024 * 1024:
                raise ValueError("Not a supported Mach-O executable")
            handle.seek(32)
            commands = handle.read(size)
            result = {
                "format": "Mach-O64", "system": "Darwin",
                "architecture": {0x100000C: "arm64", 0x1000007: "x86_64"}.get(cpu, "unknown"),
                "minimum_os": None, "dynamic_libraries": [],
            }
            offset = 0
            for _ in range(ncmds):
                if offset + 8 > len(commands):
                    raise ValueError("Truncated Mach-O command table")
                command, length = struct.unpack_from("<II", commands, offset)
                if length < 8 or offset + length > len(commands):
                    raise ValueError("Invalid Mach-O command length")
                data = commands[offset:offset + length]
                if command in (0x32, 0x24) and length >= 16:
                    version = struct.unpack_from("<I", data, 12 if command == 0x32 else 8)[0]
                    result["minimum_os"] = "%d.%d.%d" % (
                        version >> 16, (version >> 8) & 255, version & 255)
                if command in (0xC, 0x80000018, 0x8000001F) and length >= 24:
                    name_offset = struct.unpack_from("<I", data, 8)[0]
                    result["dynamic_libraries"].append(
                        data[name_offset:].split(b"\x00", 1)[0].decode("utf-8", errors="replace"))
                offset += length
            return result
        if len(header) >= 64 and header[:2] == b"MZ":
            handle.seek(struct.unpack_from("<I", header, 60)[0])
            pe = handle.read(26)
            if len(pe) != 26 or pe[:4] != b"PE\x00\x00":
                raise ValueError("Invalid PE header")
            machine = struct.unpack_from("<H", pe, 4)[0]
            magic = struct.unpack_from("<H", pe, 24)[0]
            if magic not in (0x10B, 0x20B):
                raise ValueError("Unsupported PE optional header")
            return {
                "format": "PE32+" if magic == 0x20B else "PE32", "system": "Windows",
                "architecture": {0x8664: "x86_64", 0xAA64: "arm64", 0x14C: "x86"}.get(machine, "unknown"),
                "minimum_os": None, "dynamic_libraries": None,
            }
    raise ValueError("Unsupported binary format (expected Mach-O64 or PE)")


def normalized_architecture(machine):
    value = machine.lower()
    return {"amd64": "x86_64", "aarch64": "arm64"}.get(value, value)


def bundled_path(root, relative):
    base = Path(root).resolve()
    path = (base / relative).resolve()
    try:
        path.relative_to(base)
    except ValueError:
        raise ValueError("Manifest path escapes the skill directory: " + str(relative))
    return path


def load_manifest(root=SKILL_ROOT):
    path = Path(root) / "bin" / "manifest.json"
    with path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("schema_version") != "1" or not isinstance(manifest.get("engines"), list):
        raise ValueError("Unsupported engine manifest schema")
    ids = [item["id"] for item in manifest["engines"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate engine IDs")
    for item in manifest["engines"]:
        bundled_path(root, item["path"])
    return manifest


def select_engine(manifest, system, architecture):
    matches = [item for item in manifest["engines"]
               if item["system"] == system and item["architecture"] == architecture]
    if len(matches) != 1:
        raise ValueError("Expected one bundled engine for %s/%s; found %d" % (
            system, architecture, len(matches)))
    return matches[0]


def find_rscript():
    candidates = [os.environ.get("BLINK_AI_RSCRIPT"),shutil.which("Rscript")]
    candidates.extend(parent/".runtime/Rscript" for parent in list(SKILL_ROOT.parents)[:4])
    if platform.system() == "Darwin":
        candidates.append("/Library/Frameworks/R.framework/Resources/bin/Rscript")
    if platform.system() == "Windows":
        base=Path(os.environ.get("ProgramFiles","C:/Program Files"))/"R"
        candidates.extend(sorted(base.glob("R-*/bin/Rscript.exe"),reverse=True))
    for value in candidates:
        if value and Path(value).is_file() and os.access(value, os.X_OK):
            return str(Path(value).resolve())
    return None


def inspect_environment(root=SKILL_ROOT, profile="engine", project_root=None):
    system = platform.system()
    architecture = normalized_architecture(platform.machine())
    checks = []

    def check(name, passed, detail, required=True):
        checks.append({"id": name, "passed": bool(passed), "required": required, "detail": detail})

    result = {
        "schema_version": "1", "tool_version": VERSION, "inspected_at": utc_now(),
        "profile": profile, "inspection_executes_blink": False,
        "host": {"system": system, "architecture": architecture,
                 "os_version": platform.mac_ver()[0] if system == "Darwin" else platform.release(),
                 "python_version": platform.python_version(), "python_executable": sys.executable},
        "engine": None, "rscript": None, "checks": checks,
    }
    check("python_version", sys.version_info >= (3, 9), "Python 3.9 or later required")
    try:
        manifest = load_manifest(root)
        engine = select_engine(manifest, system, architecture)
        path = bundled_path(root, engine["path"])
        result["engine"] = dict(engine, resolved_path=str(path))
        check("manifest", True, "One native engine selected")
        actual_hash = sha256_file(path)
        result["engine"]["actual_sha256"] = actual_hash
        check("binary_integrity", actual_hash == engine["sha256"], "Bundled SHA-256 must match the manifest")
        metadata = binary_metadata(path)
        result["engine"]["observed_metadata"] = metadata
        check("native_binary", metadata["system"] == system and metadata["architecture"] == architecture,
              "Binary header must match host OS and architecture")
        check("executable", os.access(path, os.X_OK) if system != "Windows" else True,
              "Executable permission required on Unix")
        if system == "Darwin" and metadata["minimum_os"]:
            def version_tuple(value):
                return tuple(int(part) for part in value.split(".")) + (0,) * (3 - len(value.split(".")))
            check("minimum_os", version_tuple(platform.mac_ver()[0]) >= version_tuple(metadata["minimum_os"]),
                  "Declared minimum macOS: " + metadata["minimum_os"])
    except (OSError, ValueError, KeyError, TypeError, struct.error) as exc:
        check("engine_selection", False, str(exc))
    rscript = find_rscript()
    result["rscript"] = {"path": rscript, "version": None}
    check("rscript_available", rscript is not None, "Rscript required for GAPIT/R workflow", profile == "gwas")
    if profile == "gwas" and rscript:
        try:
            probe = subprocess.run([rscript, "--version"], capture_output=True, text=True,
                                   errors="replace", timeout=10, check=False)
            result["rscript"]["version"] = (probe.stdout + probe.stderr).strip()
            check("rscript_runs", probe.returncode == 0, "Rscript --version")
            environment = dict(os.environ)
            library_base = Path(project_root or Path.cwd()) / ".blink-ai/r-library"
            environment.setdefault("BLINK_AI_R_LIBRARY", str(library_base.resolve()))
            package_probe = ("v<-paste(R.version$major,strsplit(R.version$minor,'.',fixed=TRUE)[[1]][1],sep='.');"
                             "lib<-file.path(Sys.getenv('BLINK_AI_R_LIBRARY'),paste0('R-',v,'-',R.version$platform));"
                             ".libPaths(c(lib,.libPaths()));"
                             "quit(status=if(requireNamespace('jsonlite',quietly=TRUE)) 0 else 2)")
            probe = subprocess.run([rscript,"--vanilla","-e",package_probe],env=environment,capture_output=True,timeout=20,check=False)
            check("jsonlite",probe.returncode==0,"R package jsonlite required")
        except (OSError, subprocess.TimeoutExpired) as exc:
            check("rscript_runs", False, str(exc))
    if profile == "gwas":
        template = Path(root) / "assets/templates/BLINK_AI_GWAS_template.R"
        check("gwas_template", template.is_file(), "Complete canonical GWAS R template required")
        try:
            entries=[e for e in load_manifest(root).get("conversion_tools",[]) if (e["system"],e["architecture"])==(system,architecture)]
            if len(entries)!=1:raise ValueError("One native C preparation/conversion tool required; build both native programs")
            entry=entries[0];native=bundled_path(root,entry["path"]);metadata=binary_metadata(native)
            check("native_converter",sha256_file(native)==entry["sha256"] and (metadata["system"],metadata["architecture"])==(system,architecture),"C preparation/conversion binary integrity and native platform")
            source=Path(root)/"assets/gapit/SOURCE.json";data=json.loads(source.read_text(encoding="utf-8"))
            check("gapit_sources",all(sha256_file(source.parent/name)==digest for name,digest in data["files"].items()),"Pinned GAPIT functions must match source manifest")
        except (OSError,ValueError,KeyError,TypeError) as exc:
            check("workflow_resources",False,str(exc))
    result["ready"] = all(item["passed"] for item in checks if item["required"])
    result["status"] = ("prerequisites_available" if profile == "gwas" else "ready_for_engine_probe") if result["ready"] else "blocked"
    return result


def iter_gwas_rows(path):
    """Validate and normalize the legacy table; stream rows for large results."""
    seen = set()
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != ["taxa", "chr", "pos", "maf", "p_value"]:
            raise ValueError("Unexpected GWAS header: " + repr(reader.fieldnames))
        for line, row in enumerate(reader, 2):
            try:
                marker = row["taxa"]
                if not marker or marker in seen or None in row:
                    raise ValueError("Empty/duplicate marker or malformed row")
                chromosome, position = int(row["chr"]), int(row["pos"])
                maf, p_value = float(row["maf"]), float(row["p_value"])
                if chromosome < 1 or position < 1:
                    raise ValueError("Nonpositive chromosome or position")
                if not math.isfinite(maf) or not 0 <= maf <= 0.500001:
                    raise ValueError("Invalid MAF")
                if not math.isfinite(p_value) or not 0 <= p_value <= 1:
                    raise ValueError("Invalid P value")
            except (TypeError, ValueError, KeyError) as exc:
                raise ValueError("Invalid GWAS row %d: %s" % (line, exc)) from exc
            seen.add(marker)
            yield {"snp_id": marker, "chromosome": chromosome, "position": position,
                   "maf": maf, "p_value": p_value}
    if not seen:
        raise ValueError("GWAS table contains no marker rows")


def write_json(path, value):
    """Write one machine-readable result atomically in its existing directory."""
    target = Path(path)
    temporary = target.with_name(target.name + ".tmp-" + str(os.getpid()))
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect-environment", help="Inspect prerequisites without starting BLINK")
    inspect.add_argument("--profile", choices=("engine", "gwas"), default="engine")
    inspect.add_argument("--project-root", type=Path, default=Path.cwd())
    inspect.add_argument("--output", type=Path, help="Also save JSON to this file (parent must exist)")
    setup = sub.add_parser("setup-environment", help="Prepare the project R library and bundled GAPIT functions")
    setup.add_argument("--project-root", type=Path, default=Path.cwd())
    setup.add_argument("--rscript", type=Path)
    setup.add_argument("--no-install", action="store_true", help="Check installed packages without downloading missing dependencies")
    for action in ("feedback-create", "feedback-update"):
        p = sub.add_parser(action, help="Create or update a local feedback record")
        p.add_argument("--project-root", type=Path, default=Path.cwd())
        p.add_argument("--input", type=Path, required=True, help="JSON feedback details")
        if action == "feedback-create":
            p.add_argument("--run-dir", type=Path)
        else:
            p.add_argument("--id", required=True)
    sub.add_parser("parameters",help="List source-audited native options and equivalent configuration")
    init=sub.add_parser("init-config",help="Write a new editable GWAS config; never overwrite")
    init.add_argument("--output",type=Path,required=True)
    run=sub.add_parser("run",help="Run canonical R template and validate the complete analysis")
    run.add_argument("--config",type=Path,required=True)
    for stage in ("bootstrap","prepare","analyze","finalize","mark-failed","set-phase"):
        p=sub.add_parser(stage,help=argparse.SUPPRESS)
        p.add_argument("--config" if stage=="bootstrap" else "--run-dir",type=Path,required=True)
        if stage == "set-phase":
            p.add_argument("--phase", choices=("simulation", "plotting"), required=True)
    knowledge=sub.add_parser("search-knowledge",help="Search the bundled domain knowledge")
    knowledge.add_argument("query")
    conversion = sub.add_parser("convert", help="Convert PLINK/VCF/VCF.gz/Numeric/HapMap/BLINK through native C")
    choices = ("plink", "vcf", "vcf_gz", "numeric", "hapmap", "blink")
    conversion.add_argument("--from", dest="input_format", choices=choices, required=True)
    conversion.add_argument("--to", dest="output_format", choices=choices, required=True)
    conversion.add_argument("--input", dest="input_prefix", type=Path, required=True, help="Input file prefix without format suffix")
    conversion.add_argument("--output-dir", type=Path, required=True, help="NEW run directory; never overwrite existing data")
    conversion.add_argument("--samples", type=Path, help="Sample metadata TSV for bare Numeric/BLINK")
    conversion.add_argument("--alleles", type=Path, help="Variant metadata TSV with SNP/coordinates/ref/alt")
    conversion.add_argument("--allow-synthetic-alleles", action="store_true", help="Explicitly use placeholder A/T labels when biological alleles are unknown")
    conversion.add_argument("--allow-lossy", action="store_true", help="Explicitly permit discarded phase/non-GT VCF annotations")
    args = parser.parse_args(argv)
    if args.command == "setup-environment":
        import r_environment
        try:
            result = r_environment.setup(args.project_root, args.rscript, not args.no_install)
        except (OSError, ValueError) as error:
            import feedback
            feedback.record_failure(args.project_root, error, "Prepare the R environment for bundled GAPIT functions")
            raise
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command in ("feedback-create", "feedback-update"):
        import feedback
        details = feedback.read_json(args.input)
        if args.command == "feedback-create":
            result = feedback.create(args.project_root, details, args.run_dir)
        else:
            result = feedback.update(args.project_root, args.id, details)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "parameters":
        import analysis_config
        print(json.dumps(analysis_config.catalogue(),ensure_ascii=False,indent=2));return 0
    if args.command == "init-config":
        import analysis_config
        if args.output.exists():raise FileExistsError(str(args.output))
        write_json(args.output,analysis_config.DEFAULTS);return 0
    if args.command == "search-knowledge":
        terms=args.query.lower().split();matches=[]
        for path in sorted((SKILL_ROOT/"references").glob("*.md")):
            for i,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
                if any(term in line.lower() for term in terms):matches.append({"file":str(path),"line":i,"text":line})
        print(json.dumps(matches[:60],ensure_ascii=False,indent=2));return 0
    if args.command in ("run","bootstrap","prepare","analyze","finalize","mark-failed","set-phase"):
        import analysis_pipeline
        if args.command=="run":result=analysis_pipeline.run(args.config)
        elif args.command=="bootstrap":result=analysis_pipeline.bootstrap(args.config)
        elif args.command=="mark-failed":
            message = args.run_dir / "logs/failure.message.txt"
            result = analysis_pipeline.mark_failed(args.run_dir, message.read_text(encoding="utf-8") if message.is_file() else "R stage failed; inspect logs")
        elif args.command=="set-phase":result=analysis_pipeline.state(args.run_dir, phase=args.phase)
        else:result=getattr(analysis_pipeline,args.command)(args.run_dir)
        if args.command=="prepare":result={"samples":len(result["samples"]),"markers":len(result["variants"])}
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False));return 0
    if args.command == "convert":
        # Local import avoids loading conversion code for environment-only queries.
        import format_conversion
        try:
            result = format_conversion.convert(args.input_prefix, args.input_format, args.output_format, args.output_dir,
                                               args.samples, args.alleles, args.allow_synthetic_alleles, args.allow_lossy)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            import feedback
            try:
                feedback.record_failure(Path.cwd(), error, "Convert genotype data from " + args.input_format + " to " + args.output_format,
                                        args.output_dir if (args.output_dir / "conversion.json").is_file() else None)
            except (OSError, ValueError) as feedback_error:
                print("Cannot save local feedback: " + str(feedback_error), file=sys.stderr)
            raise
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    result = inspect_environment(profile=args.profile, project_root=args.project_root)
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)

