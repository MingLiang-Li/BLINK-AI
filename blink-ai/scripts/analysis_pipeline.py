"""Deterministic stages called by the canonical R workflow; no GWAS in Python."""
import csv
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import analysis_config as contract
import blinkc_runner as runner
import format_conversion as formats

CYCLE_REDUCTION = re.compile(r"GWAS cycle_size reduced from (\d+) to (\d+) \(iteration (\d+), next SNP (\d+)\)")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def state(root, **changes):
    path=Path(root)/"manifest.json"
    value=read_json(path);value.update(changes,updated_at=runner.utc_now());runner.write_json(path,value)
    return value


def bootstrap(config_path, skill=runner.SKILL_ROOT):
    config=contract.load_config(config_path);root=Path(config["output"]["run_dir"])
    root.mkdir(parents=True,exist_ok=False)
    for folder in ("work","logs","results","plots","simulation"):(root/folder).mkdir()
    runner.write_json(root/"config.resolved.json",config)
    shutil.copyfile(config_path,root/"config.input.json")
    template=Path(skill)/"assets/templates/BLINK_AI_GWAS_template.R"
    shutil.copyfile(template,root/"run_gwas.R")
    manifest={"schema_version":"1","version":runner.VERSION,"run_id":root.name,"status":"created","phase":"bootstrap",
              "started_at":runner.utc_now(),"config_sha256":runner.sha256_file(root/"config.resolved.json"),
              "template_sha256":runner.sha256_file(template),"skill_dir":str(skill),"commands":[],"warnings":[]}
    if len(config["engine"]["bin_size"])>1 or len(config["engine"]["bin_selection"] or [])>1:
        manifest["warnings"].append("The first bin size selects the active bin map. The first bin selection value sets the initial cap.")
    if config["engine"]["model"]=="GLM":manifest["warnings"].append("GLM uses the initial scan. Iteration settings apply to BLINK.")
    vendor=read_json(Path(skill)/"assets/gapit/SOURCE.json")
    for name,expected in vendor["files"].items():
        if runner.sha256_file(Path(skill)/"assets/gapit"/name)!=expected:raise ValueError("Pinned GAPIT source hash mismatch: "+name)
    manifest["gapit"]=vendor
    manifest["environment"] = runner.inspect_environment()
    runner.write_json(root/"manifest.json",manifest)
    return {"run_dir":str(root),"config":str(root/"config.resolved.json")}


def execute(root, argv, label, timeout=86400, cwd=None):
    root=Path(root);cwd = Path(cwd) if cwd is not None else root / "work"
    record={"argv":list(map(str,argv)),"cwd":str(cwd),"started_at":runner.utc_now(),"label":label}
    current=read_json(root/"manifest.json");current["commands"].append(record);runner.write_json(root/"manifest.json",current)
    stdout=root/"logs"/(label+".stdout.log");stderr=root/"logs"/(label+".stderr.log")
    with stdout.open("wb") as out,stderr.open("wb") as err:
        try:process=subprocess.run(record["argv"],cwd=cwd,stdout=out,stderr=err,timeout=timeout,check=False)
        except subprocess.TimeoutExpired:
            state(root,status="failed",error="Native step timed out: "+label);raise ValueError("Timed out: "+label)
    current=read_json(root/"manifest.json");current["commands"][-1].update(returncode=process.returncode,finished_at=runner.utc_now());runner.write_json(root/"manifest.json",current)
    if process.returncode:
        with stderr.open("rb") as handle:
            handle.seek(max(0, stderr.stat().st_size - 4096))
            detail = handle.read().decode("utf-8", errors="replace")[-1500:]
        raise ValueError(f"Native step failed: {label} (exit {process.returncode}): {detail}; see {stderr}")
    return stdout


def tabular(path, id_column=None):
    with Path(path).open(encoding="utf-8-sig",newline="") as handle:
        head=handle.readline();handle.seek(0)
        if "\t" in head: rows=list(csv.reader(handle,delimiter="\t"))
        elif "," in head: rows=list(csv.reader(handle))
        else: rows=[line.split() for line in handle if line.strip()]
    if len(rows)<2 or len(rows[0])<2 or len(set(rows[0]))!=len(rows[0]):raise ValueError("Invalid table header: "+str(path))
    header=rows[0];id_column=id_column or header[0]
    if id_column not in header:raise ValueError("ID column missing: "+id_column)
    id_index=header.index(id_column);data={}
    for row in rows[1:]:
        if len(row)!=len(header) or not row[id_index] or row[id_index] in data:raise ValueError("Malformed/duplicate sample row: "+str(path))
        data[row[id_index]]=dict(zip(header,row))
    return header,id_column,data


def prefixes(config):
    entry=config["input"];path=Path(entry["path"])
    if entry["layout"]=="single":return [path]
    suffix=formats.SUFFIXES[entry["format"]][0]
    if not path.is_dir():raise ValueError("Multi input.path must be a directory")
    files=list(path.glob("*"+suffix))
    if entry["format"]=="hapmap" and not files:files=list(path.glob("*.hmp.txt"));suffix=".hmp.txt"
    result=[];seen=set()
    for item in files:
        match=re.match(r"^(\d+)",item.name)
        if not match:raise ValueError("Chunk name needs a leading numeric prefix: "+item.name)
        number=int(match.group(1))
        if number in seen:raise ValueError("Duplicate chunk numeric prefix")
        seen.add(number);result.append((number,Path(str(item)[:-len(suffix)])))
    if not result:raise ValueError("No genotype chunks found")
    return [path for _,path in sorted(result)]


def prepare(root):
    root=Path(root);config=read_json(root/"config.resolved.json");entry=config["input"]
    state(root,status="running",phase="prepare")
    env=runner.inspect_environment()
    if not env["ready"]:raise ValueError("Native engine environment unavailable")
    tools=runner.load_manifest().get("conversion_tools",[])
    tool=next((x for x in tools if x["system"]==env["host"]["system"] and x["architecture"]==env["host"]["architecture"]),None)
    if not tool:raise ValueError("Native conversion extension missing; rebuild native binaries")
    native=runner.bundled_path(runner.SKILL_ROOT,tool["path"])
    if runner.sha256_file(native)!=tool["sha256"]:raise ValueError("Conversion extension hash mismatch")
    sources=prefixes(config);samples=None;all_variants=[];parts=root/"work/parts";parts.mkdir();source_records=[];qc_summaries=[]
    for index,prefix in enumerate(sources,1):
        converted=root/"work"/("convert_%03d"%index)
        formats.convert(prefix,entry["format"],"blink",converted,entry["samples"],entry["alleles"],entry["allow_synthetic_alleles"],entry["allow_lossy"])
        source=converted/"output/data";meta=formats.inspect_input(source,"blink")
        if samples is None:samples=meta["samples"]
        elif samples!=meta["samples"]:raise ValueError("Sample identities/order differ in chunk "+str(prefix))
        keep=config["samples"]["keep"] or [s["sample_id"] for s in samples]
        ids=[s["sample_id"] for s in samples]
        if len(set(keep))!=len(keep) or set(keep)-set(ids):raise ValueError("Unknown/repeated samples.keep IDs")
        selection=root/"work/selected_indices.txt"
        selection.write_text("\n".join(str(ids.index(value)) for value in keep)+"\n",encoding="ascii")
        target=parts/("%03d_chunk"%index)
        qc=config["qc"]
        log=execute(root,[native,"--prepare",source, target,formats.ext(source,".samples.tsv"),formats.ext(source,".variants.tsv"),selection,
                          qc["genotype_missing"],qc["maf_min"],qc["missing_max"]],"prepare_%03d"%index)
        summary=read_json(log);qc_summaries.append(summary)
        source_records.append({"path":str(prefix),"input_hashes":read_json(converted/"conversion.json")["input_files"],
                               "information_changes":meta["information_changes"],"qc":summary})
        if not summary["markers_retained"]:
            for file in parts.glob(target.name+".*"):file.unlink()
            continue
        prepared=formats.inspect_input(target,"blink")
        if all_variants and {v["snp_id"] for v in prepared["variants"]}.intersection(v["snp_id"] for v in all_variants):raise ValueError("Duplicate marker IDs across chunks")
        all_variants.extend(prepared["variants"])
    if not all_variants:raise ValueError("No marker passed genotype QC")
    selected=[samples[[s["sample_id"] for s in samples].index(value)] for value in keep]
    if len(selected)<4:raise ValueError("GWAS requires at least four selected samples")
    hub=root/"work/genotype"
    if len(sources)>1:
        execute(root,[env["engine"]["resolved_path"],"--multi","--file",parts,"--out",hub,"--binary","--compress"],"merge",config["runtime"]["timeout_seconds"])
    else:
        actual=next(parts.glob("*.pre"));base=Path(str(actual)[:-4])
        for suffix in formats.SUFFIXES["blink"]:shutil.copyfile(formats.ext(base,suffix),formats.ext(hub,suffix))
    formats.write_tsv(formats.ext(hub,".samples.tsv"),formats.SAMPLE_HEADER,selected)
    formats.write_tsv(formats.ext(hub,".variants.tsv"),formats.VARIANT_HEADER,all_variants)
    formats.canonical_inf(hub,selected,all_variants)
    formats.blink_digest(hub,len(selected),len(all_variants))
    # BLINK's integer chromosome representation is encoded explicitly, preserving labels.
    chromosomes=list(dict.fromkeys(v["chromosome"] for v in all_variants));chromosome_codes={value:i+1 for i,value in enumerate(chromosomes)}
    with formats.ext(hub,".map").open("w",encoding="utf-8",newline="\n") as handle:
        handle.write("rs\tchr\tpos\n")
        for row in all_variants:handle.write("%s\t%d\t%s\n"%(row["snp_id"],chromosome_codes[row["chromosome"]],row["position"]))
    if config["simulation"]["enabled"]:
        if len(selected)*len(all_variants)>config["simulation"]["max_cells"]:raise ValueError("Simulation exceeds max_cells; explicit bounded GD required")
        if config["simulation"]["nqtn"]>len(all_variants):raise ValueError("simulation.nqtn exceeds retained markers")
        execute(root,[native,hub,formats.ext(hub,".samples.tsv"),formats.ext(hub,".variants.tsv"),"numeric",root/"simulation/genotypes",len(all_variants)],"simulation_genotypes")
    context={"genotype":str(hub),"samples":selected,"variants":all_variants,"chromosome_codes":chromosome_codes,
             "sources":source_records,"environment":env,"converter_sha256":tool["sha256"],"qc":qc_summaries}
    runner.write_json(root/"context.json",context)
    state(root,phase="prepared",sample_count=len(selected),marker_count=len(all_variants),engine=env["engine"],
          converter_sha256=tool["sha256"],sources=source_records)
    return context


def run_gwas_batch(root, index, engine, hub, parameters, marker_ids, deadline):
    """Run one BLINK process and collect its in-process block reductions."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError("GWAS time budget exhausted before the next batch")
    label = f"gwas_{index:04d}"
    batch_dir = root / "work" / label
    batch_dir.mkdir()
    prefix = batch_dir / "scan"
    argv = contract.engine_argv(engine, hub, prefix, parameters, index, marker_ids)
    execute(root, argv, label, remaining, cwd=batch_dir)

    initial_size = min(parameters["cycle_size"], len(marker_ids))
    reductions = []
    with formats.ext(prefix, ".log").open(encoding="utf-8", errors="replace") as native_log:
        for line in native_log:
            event = CYCLE_REDUCTION.fullmatch(line.rstrip())
            if event:
                before, after, iteration, marker = map(int, event.groups())
                reductions.append({"from": before, "to": after, "iteration": iteration, "next_snp": marker})
    return prefix, {
        "initial_cycle_size": initial_size,
        "cycle_size": reductions[-1]["to"] if reductions else initial_size,
        "cycle_size_reductions": reductions,
    }


def analyze(root):
    root=Path(root);cfg=read_json(root/"config.resolved.json");context=read_json(root/"context.json")
    state(root,phase="gwas")
    phenotype=root/"simulation/phenotype.tsv" if cfg["simulation"]["enabled"] else Path(cfg["phenotype"]["path"])
    header,id_column,data=tabular(phenotype,cfg["phenotype"]["id_column"])
    names=[name for name in header if name!=id_column]
    selected_names=cfg["phenotype"]["traits"]
    if selected_names is None:
        index=cfg["engine"]["trait"]
        if index>len(names):raise ValueError("engine.trait exceeds phenotype columns")
        selected_names=names if index==0 else [names[index-1]]
    if not isinstance(selected_names,list) or not selected_names or set(selected_names)-set(names) or len(set(selected_names))!=len(selected_names):raise ValueError("Unknown/repeated phenotype traits")
    samples=context["samples"];ids=[s["sample_id"] for s in samples]
    if set(ids)-set(data):raise ValueError("Phenotype missing sample IDs: "+", ".join(sorted(set(ids)-set(data))[:10]))
    def number(value,allow_missing):
        if value in ("","NA","NaN","nan","."):
            if allow_missing:return "nan"
            raise ValueError("Missing phenotype/covariate value")
        numeric=float(value)
        if not math.isfinite(numeric):raise ValueError("Non-finite phenotype/covariate")
        return format(numeric,".17g")
    hub=Path(context["genotype"]);internal={name:"T%04d"%(i+1) for i,name in enumerate(names)};counts={}
    with formats.ext(hub,".txt").open("w",encoding="utf-8",newline="\n") as handle:
        handle.write("taxa "+" ".join(internal[name] for name in names)+"\n")
        for name in selected_names:
            values=[number(data[s][name],cfg["phenotype"]["missing"]=="exclude_per_trait") for s in ids]
            counts[name]=sum(value!="nan" for value in values)
            if len(set(value for value in values if value!="nan"))<2:raise ValueError("Constant/empty phenotype: "+name)
        for sample in ids:handle.write(sample+" "+" ".join(number(data[sample][name],True) for name in names)+"\n")
    cov_names=[]
    if cfg["covariates"]["path"]:
        cov_head,cov_id,cov_data=tabular(cfg["covariates"]["path"],cfg["covariates"]["id_column"])
        cov_names=cfg["covariates"]["columns"] or [name for name in cov_head if name!=cov_id]
        if set(ids)-set(cov_data) or set(cov_names)-set(cov_head):raise ValueError("Covariates have missing IDs/columns")
        columns=[[float(number(cov_data[s][name],False)) for s in ids] for name in cov_names]
        if not cov_names or len(set(cov_names))!=len(cov_names) or cov_id in cov_names or len(cov_names)+3>=len(ids):
            raise ValueError("Invalid/repeated covariates or insufficient residual degrees of freedom")
        # Check full rank including intercept using stable elimination; no external Python dependencies.
        for trait in selected_names:
            observed=[i for i,s in enumerate(ids) if number(data[s][trait],True)!="nan"]
            if len(observed)<=len(cov_names)+3:raise ValueError("Too few observed samples for covariates")
            matrix=[[1.0]+[column[i] for column in columns] for i in observed];rank=0
            for j in range(len(cov_names)+1):
                pivot=max(range(rank,len(matrix)),key=lambda i:abs(matrix[i][j]))
                if abs(matrix[pivot][j])<1e-10:raise ValueError("Covariates are constant/linearly dependent for trait "+trait)
                matrix[rank],matrix[pivot]=matrix[pivot],matrix[rank];scale=matrix[rank][j]
                matrix[rank]=[v/scale for v in matrix[rank]]
                for i in range(rank+1,len(matrix)):
                    factor=matrix[i][j];matrix[i]=[a-factor*b for a,b in zip(matrix[i],matrix[rank])]
                rank+=1
        with formats.ext(hub,".cov").open("w",encoding="utf-8",newline="\n") as handle:
            handle.write("taxa "+" ".join("C%d"%i for i in range(len(cov_names)))+"\n")
            for sample in ids:handle.write(sample+" "+" ".join(number(cov_data[sample][name],False) for name in cov_names)+"\n")
    if any(counts[name]<=len(cov_names)+3 for name in selected_names):raise ValueError("Too few observed samples after accounting for covariates")
    marker_ids=[v["snp_id"] for v in context["variants"]]
    batches=[(0,selected_names)] if cfg["phenotype"]["traits"] is None and cfg["engine"]["trait"]==0 else [(names.index(name)+1,[name]) for name in selected_names]
    rows=[]
    deadline = time.monotonic() + cfg["runtime"]["timeout_seconds"]
    parameters = dict(cfg["engine"])
    completed_batches = []
    for index,batch in batches:
        prefix, sizing = run_gwas_batch(root, index, context["environment"]["engine"]["resolved_path"],
                                       hub, parameters, marker_ids, deadline)
        if sizing["cycle_size_reductions"]:
            parameters["cycle_size"] = sizing["cycle_size"]
        for name in batch:
            result=Path(str(prefix)+"_"+internal[name]+"_GWAS_result.txt")
            current=list(runner.iter_gwas_rows(result))
            if [r["snp_id"] for r in current]!=marker_ids:raise ValueError("GWAS result marker set/order differs from prepared input")
            for value,meta in zip(current,context["variants"]):
                if value["chromosome"]!=context["chromosome_codes"][meta["chromosome"]] or value["position"]!=int(meta["position"]):raise ValueError("GWAS coordinates differ from prepared input")
                value.update(chromosome=meta["chromosome"],trait=name,trait_id=internal[name]);rows.append(value)
        completed_batches.append({"traits": batch, **sizing})
    formats.write_tsv(root/"results/gwas.tsv",["snp_id","chromosome","position","maf","p_value","trait","trait_id"],rows)
    traits=[{"name":name,"id":internal[name],"observed_samples":counts[name]} for name in selected_names]
    runner.write_json(root/"results/traits.json",traits)
    state(root,phase="gwas_completed",traits=traits,gwas_batches=completed_batches,covariate_names=cov_names,ignored_phenotype_samples=sorted(set(data)-set(ids)))
    return {"traits":traits,"rows":len(rows)}


def finalize(root):
    root=Path(root);cfg=read_json(root/"config.resolved.json");manifest=read_json(root/"manifest.json")
    summary=read_json(root/"results/summary.json")
    plotting = read_json(root / "results/plotting.json")
    if (plotting.get("provider"), plotting.get("manhattan_function"), plotting.get("qq_function")) != ("GAPIT", "GAPIT.Manhattan", "GAPIT.QQ"):
        raise ValueError("Expected Manhattan and QQ plots generated with the bundled GAPIT functions")
    context=read_json(root/"context.json")
    records=summary["traits"]
    if isinstance(records,dict):records=[records]
    for record in records:
        for suffix in ("manhattan.pdf","qq.pdf"):
            file=root/"plots"/(record["id"]+"_"+suffix)
            if not file.is_file() or file.stat().st_size<100:raise ValueError("Required plot missing/empty: "+str(file))
    lines = [
        "# BLINK-AI GWAS report", "", f"Run `{manifest['run_id']}`", "",
        "BLINK_c computes the associations. The bundled GAPIT functions support simulation and plotting.", "",
        "| Trait | Samples | Tested SNPs | Significant SNPs | Minimum P | Lambda (1 df) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for record in records:
        trait = str(record["name"]).replace("|", "\\|")
        lines.append("| %s | %s | %s | %s | %.6g | %s |" % (
            trait, record["samples"], record["markers"], record["significant"],
            record["minimum_p"], record.get("lambda_gc"),
        ))
    report = cfg["report"]
    read = sum(item["markers_read"] for item in context["qc"])
    imputed = sum(item["imputed_calls"] for item in context["qc"])
    lines += [
        "", f"{report['multiple_testing']} correction was applied separately to each trait at alpha = {report['alpha']}.",
        "", f"Quality control selected {len(context['samples'])} samples, retained {len(context['variants'])} of {read} SNPs, and imputed {imputed} hard calls.",
        "", "The association results provide P values and minor allele frequencies. Effect estimates and independent causal loci require separate analysis.",
        "", "## Parameters and reproducibility", "", "```json", json.dumps(cfg["engine"], ensure_ascii=False, indent=2), "```", "",
        "See `context.json` for inputs, alignment, QC, and chromosome labels. See `manifest.json` for commands, executable hashes, and stage status.",
        "", "The solid line in the Manhattan plot shows the Bonferroni threshold. A dashed BH threshold appears when at least one test passes BH correction.", "",
    ]
    for warning in manifest["warnings"]:
        lines.append("- " + warning)
    for batch in manifest.get("gwas_batches", []):
        traits = ", ".join(batch["traits"])
        lines.append(f"- The GWAS block limit for {traits} started at {batch['initial_cycle_size']} SNPs and finished at {batch['cycle_size']} SNPs.")
        for event in batch["cycle_size_reductions"]:
            lines.append(f"  - In iteration {event['iteration']}, BLINK_c resumed at SNP {event['next_snp']} with a smaller block ({event['from']} to {event['to']} SNPs).")
    losses = sorted({change for source in context["sources"] for change in source["information_changes"]})
    for loss in losses:
        lines.append(f"- Genotype conversion recorded `{loss}`.")
    lines += ["", "## Plots and results", ""]
    for record in records:
        lines.append("- %s ([Manhattan plot](plots/%s_manhattan.pdf), [QQ plot](plots/%s_qq.pdf))" %
                     (record["name"], record["id"], record["id"]))
    lines += ["", "[Full results](results/adjusted.tsv) and [significant SNPs](results/significant.tsv)"]
    if cfg["simulation"]["enabled"]:
        lines += ["", "## Simulation evaluation", "",
                  "[Evaluation metrics](simulation/evaluation.tsv) match SNP IDs to the simulated causal set. FDP describes this simulation replicate."]
    text = "\n".join(lines) + "\n"
    (root/"report.md").write_text(text, encoding="utf-8")
    links = "".join(
        f'<p>{html.escape(record["name"])} <a href="plots/{record["id"]}_manhattan.pdf">Manhattan plot</a> '
        f'<a href="plots/{record["id"]}_qq.pdf">QQ plot</a></p>' for record in records
    )
    (root/"report.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>BLINK-AI GWAS</title>'
        '<style>body{max-width:1000px;margin:2rem auto;font:16px system-ui}pre{white-space:pre-wrap}a{color:#166}</style>'
        '<h1>BLINK-AI GWAS</h1><p><a href="results/adjusted.tsv">Full results</a> '
        '<a href="results/significant.tsv">Significant SNPs</a></p>'
        + links + "<pre>" + html.escape(text) + "</pre></html>", encoding="utf-8"
    )
    state(root,status="completed",phase="completed",finished_at=runner.utc_now(),summary=summary,plotting=plotting,
          artifacts={str(p.relative_to(root)):runner.sha256_file(p) for folder in ("results","plots") for p in (root/folder).rglob("*") if p.is_file()})
    return {"status":"completed","run_dir":str(root),"report":str(root/"report.md")}


def mark_failed(root, message):
    import feedback
    root = Path(root)
    manifest = read_json(root / "manifest.json")
    config = read_json(root / "config.resolved.json")
    phase = manifest.get("failed_phase", manifest.get("phase", "unknown"))
    state(root, status="failed", failed_phase=phase, error=message)
    runner.write_json(root / "failure.json", {"phase": phase, "error": message, "at": runner.utc_now()})
    if not manifest.get("feedback"):
        project = config["runtime"]["project_root"] or Path(config["config_file"]).parent
        try:
            feedback.record_failure(project, message, "Run the configured BLINK-AI GWAS workflow", root,
                                    config["feedback"]["user_request"], config["feedback"]["user_experience"])
        except (OSError, ValueError) as error:
            state(root, feedback_error=str(error))
    return {"status": "failed", "run_dir": str(root)}


def run(config_path):
    import feedback
    import r_environment
    config_path = Path(config_path).resolve()
    cfg = None
    root = None
    owned = False
    try:
        cfg = contract.load_config(config_path)
        root = Path(cfg["output"]["run_dir"])
        if root.exists():
            raise FileExistsError("Run directory already exists: " + str(root))
        bootstrap(config_path)
        owned = True
        project = cfg["runtime"]["project_root"] or config_path.parent
        state(root, phase="environment")
        info = r_environment.setup(project, cfg["runtime"]["rscript"], log_dir=root / "logs")
        environment = r_environment.process_environment(info)
        environment["BLINK_AI_RUN_DIR"] = str(root)
        template = runner.SKILL_ROOT / "assets/templates/BLINK_AI_GWAS_template.R"
        invocation = [info["rscript"], "--vanilla", str(template), str(config_path), str(runner.SKILL_ROOT)]
        with (root / "logs/R.stdout.log").open("wb") as stdout, (root / "logs/R.stderr.log").open("wb") as stderr:
            process = subprocess.run(invocation, env=environment, stdout=stdout, stderr=stderr,
                                     timeout=cfg["runtime"]["timeout_seconds"], check=False)
        state(root, orchestrator={"argv": invocation, "python": sys.executable, "returncode": process.returncode})
        if process.returncode:
            detail = (root / "logs/R.stderr.log").read_text(encoding="utf-8", errors="replace")[-2500:]
            raise ValueError("R workflow failed: " + detail)
        if read_json(root / "manifest.json")["status"] != "completed":
            raise ValueError("Workflow exited without validated complete artifacts")
        return {"status": "completed", "run_dir": str(root), "report": str(root / "report.md")}
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        if owned:
            mark_failed(root, str(error))
        else:
            project = cfg["runtime"]["project_root"] if cfg else None
            context = {}
            if not cfg:
                try:
                    raw = read_json(config_path)
                    if isinstance(raw, dict) and isinstance(raw.get("feedback"), dict):
                        context = {key: value for key, value in raw["feedback"].items() if isinstance(value, str)}
                except (OSError, ValueError):
                    pass
            else:
                context = cfg["feedback"]
            try:
                feedback.record_failure(project or config_path.parent, error, "Load the GWAS configuration " + str(config_path),
                                        request=context.get("user_request"), experience=context.get("user_experience"))
            except (OSError, ValueError) as feedback_error:
                print("Cannot save local feedback: " + str(feedback_error), file=sys.stderr)
        raise
