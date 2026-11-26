#!/usr/bin/env Rscript
# Canonical BLINK-AI GWAS template, v0.2.7.
# Read this entire template before adapting a user analysis. Edit JSON configuration;
# preserve ID alignment, native GWAS, post-run output checks and reporting stages.
# Usage: Rscript --vanilla BLINK_AI_GWAS_template.R config.json /absolute/skill/blink-ai
args <- commandArgs(trailingOnly=TRUE)
if(length(args)<2)stop("Usage: template.R config.json /absolute/skill/blink-ai")
skill <- normalizePath(args[2],mustWork=TRUE);config <- normalizePath(args[1],mustWork=TRUE)
source(file.path(skill,"scripts/setup_r_environment.R"))
r_environment <- blink_prepare_r(
  Sys.getenv("BLINK_AI_R_LIBRARY", unset=file.path(dirname(config),".blink-ai/r-library")),
  install=tolower(Sys.getenv("BLINK_AI_INSTALL_R_PACKAGES",unset="true"))!="false",
  repository=Sys.getenv("BLINK_AI_CRAN_MIRROR",unset="https://cloud.r-project.org"))
python <- Sys.getenv("BLINK_AI_PYTHON",unset=Sys.which("python3"))
if(!nzchar(python))python <- Sys.which("python")
if(!nzchar(python))stop("Python 3.9+ required; set BLINK_AI_PYTHON")
runner <- file.path(skill,"scripts/blinkc_runner.py")
stage <- function(name,flag,value,...) {
  err <- tempfile();on.exit(unlink(err))
  output <- system2(python,args=shQuote(c(runner,name,flag,value,...)),stdout=TRUE,stderr=err)
  if(!is.null(attr(output,"status")) && attr(output,"status")!=0)stop(paste(readLines(err,warn=FALSE),collapse="\n"))
  jsonlite::fromJSON(paste(output,collapse="\n"),simplifyVector=FALSE)
}
root <- Sys.getenv("BLINK_AI_RUN_DIR",unset=NA_character_)
if(is.na(root))root <- NULL
tryCatch({
  if(is.null(root)) {
    boot <- stage("bootstrap","--config",config);root <- boot$run_dir
  }
  cfg <- jsonlite::fromJSON(file.path(root,"config.resolved.json"),simplifyVector=FALSE)
  if(!file.exists(file.path(root,"logs/r-environment.json")))
    jsonlite::write_json(r_environment,file.path(root,"logs/r-environment.json"),auto_unbox=TRUE,pretty=TRUE)
  stage("prepare","--run-dir",root)
  context <- jsonlite::fromJSON(file.path(root,"context.json"),simplifyVector=FALSE)
  source(file.path(skill,"scripts/gapit_adapter.R"))
  gapit <- blink_load_gapit(skill)
  if(cfg$simulation$enabled) {
    stage("set-phase","--run-dir",root,"--phase","simulation")
    blink_simulate(root,cfg,context,gapit)
  }
  stage("analyze","--run-dir",root)
  stage("set-phase","--run-dir",root,"--phase","plotting")
  blink_summarize(root,cfg,context,gapit)
  jsonlite::write_json(list(R=R.version.string,jsonlite=as.character(packageVersion("jsonlite")),
      gapit=jsonlite::fromJSON(file.path(skill,"assets/gapit/SOURCE.json")),
      session=capture.output(sessionInfo())),file.path(root,"results/R-session.json"),auto_unbox=TRUE,pretty=TRUE)
  done <- stage("finalize","--run-dir",root)
  cat(jsonlite::toJSON(done,auto_unbox=TRUE,pretty=TRUE),"\n")
},error=function(e) {
  if(!is.null(root)) {
    writeLines(conditionMessage(e),file.path(root,"logs/failure.message.txt"),useBytes=TRUE)
    try(stage("mark-failed","--run-dir",root),silent=TRUE)
  }
  stop(conditionMessage(e),call.=FALSE)
})
