# R dependencies used by the bundled GAPIT simulation and plotting functions.
blink_prepare_r <- function(library_base, install = TRUE, repository = "https://cloud.r-project.org") {
  version <- paste(R.version$major, strsplit(R.version$minor, ".", fixed=TRUE)[[1]][1], sep=".")
  library <- file.path(library_base, paste0("R-", version, "-", R.version$platform))
  dir.create(library, recursive=TRUE, showWarnings=FALSE)
  if(!dir.exists(library)) stop("Cannot create the project R library")
  .libPaths(c(normalizePath(library, winslash="/"), .libPaths()))
  installed <- character()
  if(!requireNamespace("jsonlite", quietly=TRUE)) {
    if(!install) stop("R package jsonlite is missing and package installation is disabled")
    options(timeout=max(120, getOption("timeout")))
    install.packages("jsonlite", lib=library, repos=repository, dependencies=NA)
    if(!requireNamespace("jsonlite", quietly=TRUE)) stop("R package jsonlite could not be installed")
    installed <- "jsonlite"
  }
  for(package in c("stats", "graphics", "grDevices", "utils"))
    if(!requireNamespace(package, quietly=TRUE)) stop(paste("Required R package is unavailable", package))
  list(R=R.version.string, platform=R.version$platform, library=normalizePath(library, winslash="/"),
       library_paths=.libPaths(), jsonlite=as.character(packageVersion("jsonlite")), installed=installed)
}

if(sys.nframe()==0L) {
  args <- commandArgs(TRUE)
  if(length(args)!=4L) stop("Expected skill directory, library directory, install flag, and CRAN mirror")
  info <- blink_prepare_r(args[2], args[3]=="true", args[4])
  source(file.path(args[1], "scripts", "gapit_adapter.R"))
  gapit <- blink_load_gapit(args[1])
  stopifnot(is.function(gapit$GAPIT.Manhattan), is.function(gapit$GAPIT.QQ),
            is.function(gapit$GAPIT.Phenotype.Simulation))
  info$plotting <- list(provider="GAPIT", manhattan="GAPIT.Manhattan", manhattan_style="Oceanic",
                        qq="GAPIT.QQ", qq_style="rainbow")
  cat(jsonlite::toJSON(info, auto_unbox=TRUE), "\n")
}
