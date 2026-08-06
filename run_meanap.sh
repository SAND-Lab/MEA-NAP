#!/bin/bash
#SBATCH --job-name=meanap
#SBATCH --output=meanap-%j.log
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --partition=Main

# Submit MEA-NAP as a batch job.
#
# Usage:
#   sbatch run_meanap.sh <MATLAB_SCRIPT_NAME>
#
# <MATLAB_SCRIPT_NAME> is the .m file to run, WITHOUT the .m extension, e.g.:
#   sbatch run_meanap.sh MEApipeline_headless_fromStep2
#   sbatch run_meanap.sh MEApipeline_headless_full
#
# That script must already exist in MEANAP_DIR (below) with its own
# "EDIT PER DATASET" block at the top pointing at the right data/output
# paths for this run -- this .sh file itself is dataset-agnostic.
#
# Notes for adapting to a different cluster (see the accompanying
# CLUSTER_SUBMISSION.md for the full writeup):
#   - --partition=Main is specific to this cluster; find the right one
#     with `sinfo`, or drop the line to use the cluster's default.
#   - The MATLAB module/path below (matlab_2020b) is specific to this
#     cluster too -- see CLUSTER_SUBMISSION.md for why R2020b specifically.
#   - Step 3 (functional connectivity) uses MATLAB's parfor, which on this
#     cluster auto-starts a SLURM-integrated parallel pool (12 workers,
#     submitted as their own sub-jobs) via a site-wide default cluster
#     profile -- nothing in MEA-NAP's own code requests this. On a cluster
#     without that MATLAB Parallel Server integration, parfor instead
#     starts a *local* pool using cores on this same node, so bump
#     --cpus-per-task up (e.g. 12+) if you want Step 3 to parallelize there.
#
# IMPORTANT gotcha found the hard way: this script's own --mem directive sets
# SLURM_MEM_PER_NODE in the environment, which this JOB's child process (the
# MATLAB session) inherits -- and the parallel-pool worker job that MATLAB's
# 'CBU_Slurm_2018' profile submits from inside that session (as its own
# nested `sbatch`) also gets its own per-CPU memory default from the
# cluster. Having both a *_PER_NODE and a *_PER_CPU memory setting active
# for that nested job makes SLURM refuse to launch it ("SLURM_MEM_PER_CPU,
# SLURM_MEM_PER_GPU, and SLURM_MEM_PER_NODE are mutually exclusive"), and
# because MATLAB's wrapper script doesn't check that srun call's exit code,
# the whole run just hangs in Step 3 until this job's own --time limit
# kills it -- no error is ever printed to this job's own log. Unsetting the
# SLURM_MEM_PER_* vars right before invoking MATLAB (below) breaks that
# inheritance so the nested job gets a clean environment. This only bites
# `sbatch`-submitted runs -- an interactive `matlab -batch` on the login
# node has no such variables set in the first place, which is why testing
# interactively there won't reveal this.

set -euo pipefail

MEANAP_DIR="/home/ad04/GitHub/MEA-NAP"
MATLAB_BIN="/hpc-software/bin/matlab_2020b"

SCRIPT_NAME="${1:?Usage: sbatch run_meanap.sh <MATLAB_SCRIPT_NAME (no .m)>}"

cd "$MEANAP_DIR"
unset SLURM_MEM_PER_NODE SLURM_MEM_PER_CPU SLURM_MEM_PER_GPU
"$MATLAB_BIN" -batch "$SCRIPT_NAME"
