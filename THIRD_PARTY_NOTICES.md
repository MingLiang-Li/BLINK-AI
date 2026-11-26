# Third-party notices

## BLINK

BLINK-AI includes BLINK_c executables for genome-wide association analysis. Author credits appear in the executable's startup banner. The native conversion executable supports genotype import, export, and preparation.

Written by: Mingliang Li. Designed by: You Tang, Meng Huang, Zhiwu Zhang.

The BLINK method is described in *BLINK: a package for the next level of genome-wide association studies with both individuals and markers in the millions*. See the [publication](https://doi.org/10.1093/gigascience/giy154) and [BLINK website](https://zzlab.net/blink/index.html).

## GAPIT

The skill includes `GAPIT.Pruning.R`, `GAPIT.Phenotype.Simulation.R`, `GAPIT.Manhattan.R`, and `GAPIT.QQ.R` from GAPIT. These functions retain their upstream author credits. The upstream package declares GNU GPL version 2 or later.

The bundled [license text](blink-ai/assets/gapit/GPL-2.txt) and [component metadata](blink-ai/assets/gapit/SOURCE.json) accompany the R functions. The workflow adapter uses these functions for simulation and plotting, with corrections for the chi-squared genomic inflation factor and BH plot threshold.

See the [GAPIT repository](https://github.com/jiabowang/GAPIT) for upstream documentation.

## External dependencies

Python and R are installed separately. The environment setup can install `jsonlite` in the project R library. Each dependency retains its respective license. The GAPIT license statement applies to the GAPIT components identified above.
