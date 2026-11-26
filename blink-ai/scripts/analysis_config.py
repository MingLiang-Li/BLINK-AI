"""Versioned BLINK_c parameter contract and strict analysis configuration."""
import copy
import json
import math
from pathlib import Path

DEFAULTS = {
    "schema_version": "1", "input": {"format": "vcf", "layout": "single", "path": "", "samples": None, "alleles": None,
                                       "allow_lossy": False, "allow_synthetic_alleles": False},
    "phenotype": {"path": None, "id_column": None, "traits": None, "missing": "exclude_per_trait"},
    "covariates": {"path": None, "id_column": None, "columns": None},
    "samples": {"keep": None},
    "engine": {"model": "BLINK", "trait": 1, "cycle_size": 2000, "max_loop": 10,
               "bin_size": [0.000001], "bin_selection": None,
               "prior": [], "cov": 1, "cutoff": 0.01},
    "qc": {"maf_min": 0.01, "missing_max": 1.0, "genotype_missing": "reject"},
    "simulation": {"enabled": False, "seed": 20261105, "h2": 0.75, "nqtn": 10, "qtn_distribution": "normal",
                   "max_cells": 5000000},
    "report": {"alpha": 0.05, "multiple_testing": "bonferroni", "correction_scope": "per_trait", "plot_dpp": 50000,"plot_seed":20261105},
    "runtime": {"rscript": None, "timeout_seconds": 86400, "project_root": None},
    "feedback": {"user_request": None, "user_experience": None}, "output": {"run_dir": ""}
}


def catalogue():
    active = [
        ("--file", "input.path", "Input prefix/directory; staged safely for the engine"),
        ("--out", "output.run_dir", "Output prefix owned by this run"),
        ("--hapmap/--vcf/--plink/--numeric/--binary", "input.format", "Import the selected genotype representation"),
        ("--uvcf/--zvcf", "input.format", "VCF text/gzip; normalized in C before import"),
        ("--multi", "input.layout", "C merges complete binary chunks before one genome-wide GWAS"),
        ("--gwas", "run/analyze command", "Actual BLINK_c computation"),
        ("--glm", "engine.model", "BLINK or GLM; GLM exits after the initial covariate-adjusted scan"),
        ("--trait", "engine.trait / phenotype.traits", "1-based index; 0 all; named trait subsets map to native indices"),
        ("--cycle_size", "engine.cycle_size", "Positive integer, initial SNPs per GWAS block. Default 2000. BLINK_c halves the effective block size and resumes at the current SNP on a cycle-buffer error."),
        ("--max_loop", "engine.max_loop", "Positive integer; native default 10"),
        ("--bin_size", "engine.bin_size", "1..30 positive values, in megabases; native default 1e-6 (1 bp); active core uses first bin map"),
        ("--bin_selection", "engine.bin_selection", "null omits flag, preserving native initial cap 1e9; when set, 1..100 positive integers, only first value sets cap; no grid search"),
        ("--prior", "engine.prior", "At most 100 post-QC 1-based indices or SNP IDs; forces initial selection evidence to 1e-100, not Bayesian priors"),
        ("--cov", "engine.cov / covariates", "1 covariates each BLINK iteration (default), 2 initial scan only; intercept is automatic"),
        ("--cutoff", "engine.cutoff", "Internal iterative candidate cutoff; distinct from report.alpha"),
        ("--keep", "samples.keep", "Select samples by ID and retain matching metadata"),
        ("--compress/--recode", "convert command", "Convert genotype formats while preserving metadata and hard calls"),
        ("--noimp", "convert / qc.genotype_missing", "Conversion preserves missingness; GWAS rejects remaining missing calls; optional explicit C mode imputation"),
    ]
    disabled = [("--pca", "Compile-time disabled in this build; supply precomputed PCs as covariates"),
                ("--parallel", "Recognized but main resets it to zero"),
                ("--host/--device", "Only consumed in disabled GPU branches; no working GPU path"),
                ("--phe/--impute", "Not parsed by this source; use phenotype.path and explicit missing policy")]
    return {"schema_version": "1", "effective": [{"flag": a, "config": b, "behavior": c} for a,b,c in active],
            "unavailable": [{"flag": a, "reason": b} for a,b in disabled],
            "limits": {"bin_size":30,"bin_selection":100,"prior":100}}


def load_config(path):
    path = Path(path).resolve()
    raw = json.loads(path.read_text(encoding="utf-8"))
    config = copy.deepcopy(DEFAULTS)
    if not isinstance(raw, dict):
        raise ValueError("Config must be a JSON object")
    for section, values in raw.items():
        if section not in config:
            raise ValueError("Unknown config section: " + section)
        if isinstance(config[section], dict):
            if not isinstance(values, dict) or set(values) - set(config[section]):
                raise ValueError("Unknown/invalid keys in config section: " + section)
            config[section].update(values)
        else:
            config[section] = values
    if config["schema_version"] != "1":
        raise ValueError("Unsupported config schema")
    for group,key in (("simulation","enabled"),("input","allow_lossy"),("input","allow_synthetic_alleles")):
        if not isinstance(config[group][key],bool):raise ValueError(group+"."+key+" must be boolean")
    for group,key in (("phenotype","traits"),("covariates","columns"),("samples","keep")):
        value=config[group][key]
        if value is not None and (not isinstance(value,list) or not value or any(not isinstance(v,str) or not v for v in value) or len(set(value))!=len(value)):
            raise ValueError(group+"."+key+" must contain distinct nonempty strings")
    def integer(value, name, minimum=1):
        if isinstance(value,bool) or not isinstance(value,int) or value < minimum or value>2147483646:
            raise ValueError(name + " must be an integer >= " + str(minimum))
    def probability(value, name, low, high):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(name + " out of range")
    if config["input"]["format"] not in ("vcf","vcf_gz","plink","hapmap","numeric","blink") or config["input"]["layout"] not in ("single","multi"):
        raise ValueError("Invalid genotype format/layout")
    for group, key in (("input","path"),("input","samples"),("input","alleles"),("phenotype","path"),("covariates","path"),("output","run_dir"),("runtime","rscript"),("runtime","project_root")):
        value=config[group][key]
        if value is not None and not isinstance(value,str):raise ValueError(group+"."+key+" must be a path string")
        if value:
            candidate=Path(value).expanduser()
            config[group][key]=str((path.parent/candidate).resolve() if not candidate.is_absolute() else candidate.resolve())
    if not config["input"]["path"] or not config["output"]["run_dir"]:
        raise ValueError("input.path and output.run_dir are required")
    for key in ("user_request", "user_experience"):
        if config["feedback"][key] is not None and not isinstance(config["feedback"][key], str):
            raise ValueError("feedback." + key + " must be a string or null")
    if not config["simulation"]["enabled"] and not config["phenotype"]["path"]:
        raise ValueError("Real-data GWAS requires phenotype.path; simulation must be explicitly enabled")
    if config["simulation"]["enabled"] and config["phenotype"]["path"]:
        raise ValueError("Choose real phenotype or explicit simulation, not both")
    engine=config["engine"]
    integer(engine["cov"],"engine.cov")
    if engine["model"] not in ("BLINK","GLM") or engine["cov"] not in (1,2):
        raise ValueError("engine.model must be BLINK/GLM; engine.cov must be 1/2")
    for key in ("cycle_size","max_loop"):integer(engine[key],"engine."+key)
    integer(engine["trait"],"engine.trait",0)
    for key, limit in (("bin_size",30),("bin_selection",100),("prior",100)):
        value=engine[key]
        if key=="bin_selection" and value is None:continue
        if not isinstance(value,list) or len(value)>limit or (key!="prior" and not value):
            raise ValueError("Invalid/too long engine."+key)
        for item in value:
            if key=="prior" and isinstance(item,str):continue
            if key=="bin_size":probability(item,key,1e-12,1e6)
            else:integer(item,key)
    probability(engine["cutoff"],"engine.cutoff",1e-300,1)
    probability(config["qc"]["maf_min"],"qc.maf_min",0,.5)
    probability(config["qc"]["missing_max"],"qc.missing_max",0,1)
    if config["qc"]["genotype_missing"] not in ("reject","mode"):
        raise ValueError("qc.genotype_missing must be reject/mode")
    if config["samples"]["keep"] is not None and (not isinstance(config["samples"]["keep"],list) or not config["samples"]["keep"]):
        raise ValueError("samples.keep must be a nonempty sample ID list")
    if config["phenotype"]["missing"] not in ("exclude_per_trait","error"):
        raise ValueError("Invalid phenotype missing policy")
    probability(config["report"]["alpha"],"report.alpha",1e-12,1)
    if config["report"]["multiple_testing"] not in ("bonferroni","BH") or config["report"]["correction_scope"]!="per_trait":
        raise ValueError("Report correction supports bonferroni/BH per trait")
    integer(config["report"]["plot_dpp"],"report.plot_dpp",100)
    integer(config["report"]["plot_seed"],"report.plot_seed",0)
    integer(config["runtime"]["timeout_seconds"],"runtime.timeout_seconds")
    sim=config["simulation"]
    integer(sim["seed"],"simulation.seed",0);integer(sim["nqtn"],"simulation.nqtn",2);integer(sim["max_cells"],"simulation.max_cells")
    probability(sim["h2"],"simulation.h2",1e-6,.999999)
    if sim["qtn_distribution"] not in ("normal","geometry"):
        raise ValueError("Unsupported QTN effect distribution")
    config["config_file"] = str(path)
    return config


def engine_argv(engine_path, prefix, output, parameters, trait, marker_ids):
    prior=[]
    for value in parameters["prior"]:
        if isinstance(value,str):
            if value not in marker_ids:raise ValueError("Prior SNP not retained after QC: "+value)
            value=marker_ids.index(value)+1
        if value<1 or value>len(marker_ids):raise ValueError("Prior index outside post-QC marker range")
        prior.append(value)
    args=[str(engine_path),"--file",str(prefix),"--out",str(output),"--binary","--gwas","--trait",str(trait),
          "--cycle_size",str(parameters["cycle_size"]),"--max_loop",str(parameters["max_loop"]),"--cov",str(parameters["cov"]),
          "--cutoff",str(parameters["cutoff"])]
    for key in ("bin_size","bin_selection"):
        if parameters[key] is None:continue
        args += ["--"+key,str(len(parameters[key]))]+list(map(str,parameters[key]))
    if prior:args += ["--prior",str(len(prior))]+list(map(str,prior))
    if parameters["model"]=="GLM":args.append("--glm")
    return args
