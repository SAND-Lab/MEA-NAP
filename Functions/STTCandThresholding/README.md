# High-performance MEX implementation of Spike Time Tiling Coefficient.
 
 *   Originally written by Catherine S Cutts (2014): https://github.com/CCutts/Detecting_pairwise_correlations_in_spike_trains/blob/master/spike_time_tiling_coefficient.c
 *   See the original paper: https://www.ncbi.nlm.nih.gov/pubmed/25339742

## IMPORTANT:

If you don't have the appropriate `.mex` version of your `.c` script (e.g. `.mexmaci64` for OSX, `.mexw64` for Windows), you need to first run in command window:

`mex sttc.c -R2018a`

---
## List of core files ##
|File            |Function      |
| ----------------|-------------|
| `sttc.c`        | Main script for STTC |
| `get_sttc.m`.   | Parses inputs from MATLAB and passes them to `sttc.c`| 
| `adjM_thr_JC.m` | Runs probabilistic thresholding of adjacency matrix output by `get_sttc.m`. Slow but with plots for troubleshooting.|
| `adjM_thr_parallel.m` | Parallel computing version of `adjM_thr_JC.m`. **Much** faster but does not support plotting.
| `significance_distribution_plots.m`| Dependency of `adjM_thr_JC.m`, plots the evolution of threshold weights over iterations|
| `cmocean.m`| Perceptually uniform (colorblind friendly) colormaps. See: https://uk.mathworks.com/matlabcentral/fileexchange/57773-cmocean-perceptually-uniform-colormaps.

---
## Auxillary files ##
* `cshift.c` runs ultra-fast circular shifts on binary arrays. Not used - requires inefficient conversion from event times to binary event matrix.
* `cshift_test.m` rough draft of some of the utilities now moved to `adjM_thr_JC.m`.

