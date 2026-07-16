"""Run the Python MEA-NAP pipeline with parameters matched to the MATLAB
parity run (parityRun/params_matlab_parity.mat), so the two runs' CSV outputs
can be compared field-by-field.

    uv run python parityRun/run_python_parity.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.params import Params
from meanap.pipeline.runner import run_pipeline


def build_params() -> Params:
    p = Params()

# ── Paths ────────────────────────────────────────────────────────────────────
    p.home_dir = str(REPO_ROOT)
    p.raw_data = str(REPO_ROOT / "ExampleData")
    p.spreadsheet_file_name = str(REPO_ROOT / "parityRun" / "exampleData_parity.csv")
    p.spreadsheet_range = "A2:A3"
    p.output_data_folder = str(REPO_ROOT / "parityRun")
    p.output_data_folder_name = "OutputData_Python_parity"

# ── Recording ────────────────────────────────────────────────────────────────
    # The bundled example recordings are 64-channel 8x8 (channels 11..88)
    # sampled at 12500 Hz -> Axion64. (The runner reads fs from the raw file
    # rather than from Params, but keep these consistent with the MATLAB run.)
    p.fs = 12500.0
    p.d_samp_f = 12500.0
    p.potential_difference_unit = "uV"
    p.channel_layout = "Axion64"

# ── Spike detection (matches params_matlab_parity.mat) ───────────────────────
    p.detect_spikes = True
    p.thresholds = [4.0, 5.0]
    p.wname_list = ["bior1.5"]
    p.cost_list = -0.12
    p.spikes_method = "bior1p5"
    p.filter_low_pass = 600.0
    p.filter_high_pass = 6150.0
    p.ref_period = 1.0
    p.get_template_ref_period = 2.0
    p.min_peak_thr_multiplier = -5.0
    p.max_peak_thr_multiplier = -100.0
    p.pos_peak_thr_multiplier = 15.0
    p.n_spikes = 10000
    p.multiple_templates = False
    p.remove_artifacts = False

# ── Activity ─────────────────────────────────────────────────────────────────
    p.min_activity_level = 0.01
    p.remove_inactive_nodes = True
    p.network_burst_detection_method = "Bakkum"
    p.min_spike_network_burst = 10
    p.min_channel_network_burst = 3
    p.bakkum_network_burst_isi_n_threshold = "automatic"
    p.single_channel_burst_detection_method = "Bakkum"
    p.single_channel_burst_min_spike = 10

# ── Functional connectivity ──────────────────────────────────────────────────
    p.func_con_lag_val = [10, 25, 50]
    p.trunc_rec = False
    p.adj_m_type = "weighted"
    p.prob_thresh_rep_num = 200
    p.prob_thresh_tail = 0.05
    p.prob_thresh_plot_checks = False

# ── Network metrics (MATLAB's netMetToCal list) ──────────────────────────────
    p.net_met_to_cal = [
    "aN", "Dens", "NDmean", "NDtop25", "sigEdgesMean", "sigEdgesTop10", "CC",
    "nMod", "Q", "PL", "Eglob", "SW", "SWw", "effRank",
    "num_nnmf_components", "nComponentsRelNS", "NSmean", "ElocMean", "PCmean",
    "PCmeanTop10", "PCmeanBottom10", "percentZscoreGreaterThanZero",
    "percentZscoreLessThanZero", "NCpn1", "NCpn2", "NCpn3", "NCpn4", "NCpn5",
    "NCpn6", "ND", "NS", "Z", "Eloc", "PC", "BC", "MEW", "aveControl",
    "modalControl", "aveControlMean",
]
    p.min_number_of_nodes_to_cal_net_met = 25
    p.exclude_edges_below_threshold = True

# ── Node cartography ─────────────────────────────────────────────────────────
    p.auto_set_cartography_boundaries = True
    p.auto_set_cartography_boundaries_per_lag = True
    p.cartography_lag_val = [10, 25, 50]
    p.hub_boundary_wm_d_deg = 0.25
    p.peri_part_coef = 0.525
    p.pro_hub_part_coef = 0.45
    p.non_hub_connector_part_coef = 0.8
    p.connector_hub_part_coef = 0.75

# ── Dimensionality ───────────────────────────────────────────────────────────
    p.eff_rank_cal_method = "Covariance"
    p.eff_rank_downsample_freq = 10.0
    p.nmf_downsample_freq = 10.0
    p.include_nmf_components = False

# ── Control ──────────────────────────────────────────────────────────────────
    p.custom_grp_order = ["NGN2"]
    p.fig_ext = [".png"]
    p.start_analysis_step = 1
    p.stop_analysis_step = 4
    p.time_processes = True

    return p


if __name__ == "__main__":
    # Guard is required: step 3/4 fan out over recordings with a process
    # pool, and without it every worker re-executes this module.
    print(run_pipeline(build_params(), log=print))
