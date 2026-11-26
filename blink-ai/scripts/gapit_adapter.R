# Pinned upstream functions plus explicit, version-checked statistical corrections.
blink_load_gapit <- function(skill) {
  path <- file.path(skill, "assets", "gapit")
  env <- new.env(parent=globalenv())
  for (name in c("GAPIT.Pruning.R", "GAPIT.Phenotype.Simulation.R", "GAPIT.Manhattan.R", "GAPIT.QQ.R")) {
    code <- paste(readLines(file.path(path,name),warn=FALSE),collapse="\n")
    if (name=="GAPIT.QQ.R") {
      old <- "lambda.estimated=median(P.values)/median(p_value_quantiles)"
      stopifnot(grepl(old,code,fixed=TRUE))
      code <- sub(old,"lambda.estimated=median(stats::qchisq(P.values,1,lower.tail=FALSE))/stats::qchisq(0.5,1)",code,fixed=TRUE)
    }
    if (name=="GAPIT.Manhattan.R") {
      old <- "FDRcutoff=-log10(cutOff*index_fdr/numMarker)"
      stopifnot(grepl(old,code,fixed=TRUE))
      code <- sub(old,"bh_pass=GI.MP[,3][stats::p.adjust(GI.MP[,3],method='BH')<=cutOff]; FDRcutoff=if(length(bh_pass)) -log10(max(bh_pass)) else NA_real_",code,fixed=TRUE)
      code <- gsub("graphics::abline(h=FDRcutoff,col=\"forestgreen\",lty=2)","if(is.finite(FDRcutoff)) graphics::abline(h=FDRcutoff,col=\"forestgreen\",lty=2)",code,fixed=TRUE)
      # Keep matrix dimensions with a single retained SNP, and keep valid P=1 tests.
      code <- gsub(",]",",,drop=FALSE]",code,fixed=TRUE)
      code <- sub("bin.mp=GI.MP[,1:3]","bin.mp=GI.MP[,1:3,drop=FALSE]",code,fixed=TRUE)
      code <- sub("index_GI=GI.MP[,3]>0","index_GI=GI.MP[,3]>=0",code,fixed=TRUE)
    }
    eval(parse(text=code),envir=env)
  }
  env
}

blink_simulate <- function(root,cfg,context,gapit) {
  # Native Numeric is SNP x sample; explicitly give GAPIT that orientation, including n==m.
  genotype <- as.matrix(read.table(file.path(root,"simulation/genotypes.dat"),header=FALSE))
  stopifnot(nrow(genotype)==length(context$variants),ncol(genotype)==length(context$samples))
  set.seed(cfg$simulation$seed)
  sim <- gapit$GAPIT.Phenotype.Simulation(GD=genotype,GM=data.frame(SNP=seq_len(nrow(genotype))),
      h2=cfg$simulation$h2,NQTN=cfg$simulation$nqtn,QTNDist=cfg$simulation$qtn_distribution,CV=NULL)
  ids <- vapply(context$samples,`[[`,"", "sample_id")
  phenotype <- data.frame(Taxa=ids,Sim=as.numeric(sim$Y[,2]))
  stopifnot(all(is.finite(phenotype$Sim)),stats::var(phenotype$Sim)>0)
  write.table(phenotype,file.path(root,"simulation/phenotype.tsv"),sep="\t",quote=FALSE,row.names=FALSE)
  qtn <- data.frame(snp_id=vapply(context$variants[sim$QTN.position],`[[`,"","snp_id"),
      post_qc_index=sim$QTN.position,effect=as.numeric(sim$effect))
  write.table(qtn,file.path(root,"simulation/truth.tsv"),sep="\t",quote=FALSE,row.names=FALSE)
  write.table(data.frame(sample_id=ids,genetic=as.numeric(sim$u),residual=as.numeric(sim$e)),
      file.path(root,"simulation/components.tsv"),sep="\t",quote=FALSE,row.names=FALSE)
}

blink_summarize <- function(root,cfg,context,gapit) {
  raw <- read.delim(file.path(root,"results/gwas.tsv"),check.names=FALSE,stringsAsFactors=FALSE)
  traits <- jsonlite::fromJSON(file.path(root,"results/traits.json"),simplifyVector=FALSE)
  summaries <- list(); adjusted <- list(); evaluations <- list(); plots <- list()
  for (i in seq_along(traits)) {
    set.seed(cfg$report$plot_seed)
    trait <- traits[[i]]; x <- raw[raw$trait_id==trait$id,,drop=FALSE]; p <- x$p_value
    x$p_bonferroni <- p.adjust(p,"bonferroni"); x$q_BH <- p.adjust(p,"BH")
    x$significant <- if(cfg$report$multiple_testing=="BH") x$q_BH<=cfg$report$alpha else x$p_bonferroni<=cfg$report$alpha
    # P=0 underflow stays zero in data. Only graph input is clamped, avoiding loss of strongest hits.
    pp <- pmax(p,.Machine$double.xmin)
    lambda <- median(qchisq(pp,1,lower.tail=FALSE))/qchisq(.5,1)
    codes <- vapply(as.character(x$chromosome),function(chr) as.numeric(context$chromosome_codes[[chr]]),0.0)
    old <- getwd();setwd(file.path(root,"plots"))
    tryCatch({
      gapit$GAPIT.Manhattan(GI.MP=data.frame(CHR=codes,BP=x$position,P=pp),name.of.trait=trait$id,
          cutOff=cfg$report$alpha,DPP=cfg$report$plot_dpp,plot.style="Oceanic")
      gapit$GAPIT.QQ(P.values=pp,name.of.trait=trait$id,DPP=cfg$report$plot_dpp,plot.style="rainbow")
    },finally=setwd(old))
    stopifnot(file.rename(file.path(root,"plots",paste0("GAPIT.Association.Manhattan_Geno.",trait$id,".pdf")),file.path(root,"plots",paste0(trait$id,"_manhattan.pdf"))))
    stopifnot(file.rename(file.path(root,"plots",paste0("GAPIT.Association.QQ.",trait$id,".pdf")),file.path(root,"plots",paste0(trait$id,"_qq.pdf"))))
    summaries[[i]] <- list(id=trait$id,name=trait$name,samples=trait$observed_samples,markers=nrow(x),
        significant=sum(x$significant),minimum_p=min(p),lambda_gc=lambda,zero_p_values=sum(p==0))
    adjusted[[i]] <- x
    plots[[i]] <- list(trait=trait$name,id=trait$id,manhattan=paste0(trait$id,"_manhattan.pdf"),qq=paste0(trait$id,"_qq.pdf"))
    if(cfg$simulation$enabled) {
      truth <- read.delim(file.path(root,"simulation/truth.tsv"),stringsAsFactors=FALSE)$snp_id
      hit <- x$snp_id[x$significant];tp <- sum(hit %in% truth);fp <- length(hit)-tp
      evaluations[[i]] <- data.frame(trait=trait$name,true_qtn=length(truth),discoveries=length(hit),TP=tp,FP=fp,
          FN=length(truth)-tp,power=tp/length(truth),FDP=if(length(hit)) fp/length(hit) else 0)
    }
  }
  all <- do.call(rbind,adjusted)
  write.table(all,file.path(root,"results/adjusted.tsv"),sep="\t",quote=FALSE,row.names=FALSE)
  write.table(all[all$significant,,drop=FALSE],file.path(root,"results/significant.tsv"),sep="\t",quote=FALSE,row.names=FALSE)
  jsonlite::write_json(list(traits=summaries,correction_scope="per_trait"),file.path(root,"results/summary.json"),auto_unbox=TRUE,pretty=TRUE,digits=16)
  jsonlite::write_json(list(provider="GAPIT",manhattan_function="GAPIT.Manhattan",manhattan_style="Oceanic",
      qq_function="GAPIT.QQ",qq_style="rainbow",traits=plots),file.path(root,"results/plotting.json"),auto_unbox=TRUE,pretty=TRUE)
  if(length(evaluations))write.table(do.call(rbind,evaluations),file.path(root,"simulation/evaluation.tsv"),sep="\t",quote=FALSE,row.names=FALSE)
}
