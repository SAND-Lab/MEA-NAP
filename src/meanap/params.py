"""Pipeline parameter definitions, mirroring the MATLAB Params struct."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class Params:
    # ── Paths ────────────────────────────────────────────────────────────────
    home_dir: str = ""
    raw_data: str = ""
    output_data_folder: str = ""
    output_data_folder_name: str = ""
    spreadsheet_file_name: str = ""
    spreadsheet_range: str = "A2:A100000"
    spike_detected_data: str = ""
    prior_analysis_path: str = ""

    # ── Recording ────────────────────────────────────────────────────────────
    fs: float = 25000.0
    d_samp_f: float = 1000.0
    potential_difference_unit: str = "uV"
    channel_layout: str = "MCS60"

    # ── Spike detection ──────────────────────────────────────────────────────
    detect_spikes: bool = True
    run_spike_check_on_prev_spike_data: bool = False
    thresholds: list[float] = field(default_factory=lambda: [4.0, 5.0])
    abs_thresholds: list[float] = field(default_factory=list)
    wname_list: list[str] = field(default_factory=lambda: ["bior1.5"])
    cost_list: float = -0.12
    spikes_method: str = "bior1p5"
    filter_low_pass: float = 600.0
    filter_high_pass: float = 8000.0
    ref_period: float = 2.0
    get_template_ref_period: float = 2.0
    min_peak_thr_multiplier: float = -5.0
    max_peak_thr_multiplier: float = -100.0
    pos_peak_thr_multiplier: float = 40.0
    n_spikes: int = 100
    multiple_templates: bool = False
    multi_template_method: str = "PCA"
    min_activity_level: float = 0.0
    remove_inactive_nodes: bool = False
    remove_artifacts: bool = False

    # ── Functional connectivity ──────────────────────────────────────────────
    func_con_lag_val: list[int] = field(default_factory=lambda: [10, 15, 25])
    trunc_rec: bool = False
    trunc_length: float = 120.0
    adj_m_type: Literal["weighted", "binary"] = "weighted"

    # ── Thresholding ─────────────────────────────────────────────────────────
    prob_thresh_rep_num: int = 200
    prob_thresh_tail: float = 0.05
    prob_thresh_plot_checks: bool = False
    prob_thresh_plot_checks_n: int = 5

    # ── Burst detection ──────────────────────────────────────────────────────
    network_burst_detection_method: str = "Bakkum"
    min_spike_network_burst: int = 10
    min_channel_network_burst: int = 3
    bakkum_network_burst_isi_n_threshold: str | float = "automatic"
    single_channel_burst_detection_method: str = "Bakkum"
    single_channel_burst_min_spike: int = 5
    single_channel_isi_threshold: str | float = "automatic"

    # ── Network metrics ──────────────────────────────────────────────────────
    net_met_to_cal: list[str] = field(default_factory=lambda: [
        "aN", "Dens", "NDmean", "NDtop25", "sigEdgesMean", "NSmean",
        "ElocMean", "CC", "nMod", "Q", "PL", "Eglob", "SW",
    ])
    recompute_metrics: bool = False
    min_number_of_nodes_to_cal_net_met: int = 3
    exclude_edges_below_threshold: bool = True

    # ── Node cartography ─────────────────────────────────────────────────────
    auto_set_cartography_boundaries: bool = True
    auto_set_cartography_boundaries_per_lag: bool = False
    cartography_lag_val: list[int] = field(default_factory=lambda: [25])
    hub_boundary_wm_d_deg: float = 2.5
    peri_part_coef: float = 0.625
    pro_hub_part_coef: float = 0.3
    non_hub_connector_part_coef: float = 0.8
    connector_hub_part_coef: float = 0.75

    # ── Dimensionality ───────────────────────────────────────────────────────
    eff_rank_cal_method: str = "ordinary"
    eff_rank_downsample_freq: float = 10.0
    nmf_downsample_freq: float = 10.0
    include_nmf_components: bool = False

    # ── Plotting ─────────────────────────────────────────────────────────────
    fig_ext: list[str] = field(default_factory=lambda: [".png"])
    show_one_fig: bool = True
    full_svg: bool = False
    raster_plot_upper_percentile: float = 99.0
    include_not_box_plots: bool = False
    include_channel_number_in_plots: bool = False
    use_theoretical_bounds: bool = True
    use_min_max_all_recording_bounds: bool = False
    use_min_max_per_genotype_bounds: bool = False
    min_node_size: float = 0.01
    max_node_size: float = 0.06
    node_scaling_method: str = "degree"
    node_scaling_power: float = 1.0
    kde_height: float = 0.3
    kde_width_for_one_point: float = 0.5
    raster_colormap: str = "parula"
    line_plot_shade_metric: str = "sem"
    custom_grp_order: list[str] = field(default_factory=list)
    network_plot_edge_threshold_method: str = "percentile"
    network_plot_edge_threshold_percentile: float = 90.0
    network_plot_edge_threshold: float = 0.1
    max_num_edges_to_plot: int = 500
    edge_subsampling_method: str = "random"
    node_layout: str = "MEA"

    # ── Pipeline control ─────────────────────────────────────────────────────
    start_analysis_step: int = 1
    stop_analysis_step: int = 4
    optional_steps_to_run: list[str] = field(default_factory=list)
    prior_analysis: bool = False
    verbose_level: str = "Normal"
    time_processes: bool = False
    output_spreadsheet_file_type: str = "csv"

    # ── Two-photon / CAT-NAP ─────────────────────────────────────────────────
    twop_activity: str = "peaks"
    twop_redo_denoising: bool = False
    remove_nodes_with_no_peaks: bool = False
    num_2p_traces: int = 3
    twop_denoising_threshold: float = 1.3
    twop_denoising_time_before_peak: float = 1.0
    twop_denoising_time_after_peak: float = 2.05
    python_path: str = ""

    # ── Stimulation ──────────────────────────────────────────────────────────
    stimulation_mode: bool = False
    automatic_stim_detection: bool = False
    stim_detection_method: str = "threshold"
    stim_detection_val: float = 2.5
    stim_refractory_period: float = 0.5
    stim_duration: float = 0.002
    stim_duration_for_plotting: float = 0.01
