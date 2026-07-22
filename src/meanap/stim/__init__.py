"""MEA-Stim: electrical stimulation detection & analysis (MATLAB port).

See ``python/MEASTIM_PORT_PLAN.md`` for the port plan and parity strategy.
"""

from .detection import (
    StimChannelInfo,
    detect_stim_times,
    get_stim_patterns,
    check_stim_pattern,
)
from .cleaning import clean_spikes_from_stim
from .psth import (
    calculate_psth_metrics,
    get_spike_latency_rel_stim,
    get_stim_artifact_duration,
    get_fr_aligned_to_stim,
)
from .activity import stim_activity_analysis, write_stim_activity_csv, CSV_COLUMNS
from .reservoir import compute_reservoir_matrices
from .shuffle import stim_shuffle_test, compute_trial_proportion
from .ssvkernel import ssvkernel
from .plotting import (
    plot_stim_times,
    plot_stim_heatmap,
    plot_stim_heatmap_w_metric,
    plot_idv_stim_data_and_trace,
    plot_stim_detection_checks,
    plot_pre_post_stim_fr,
    plot_metric_aligned_to_stim,
    plot_stim_shuffle_results,
    plot_individual_psth_and_raster,
    plot_individual_psth_and_raster_for_pattern,
    values_to_colormap,
    compute_median_spike_latency,
)
from .decoding import build_stim_activity_store, decode_patterns
from .axion import build_stim_info_from_events, read_axion_stim_csv
from .pipeline import run_stim_analysis, run_stim_analysis_for_recording

__all__ = [
    "StimChannelInfo",
    "detect_stim_times",
    "get_stim_patterns",
    "check_stim_pattern",
    "clean_spikes_from_stim",
    "calculate_psth_metrics",
    "get_spike_latency_rel_stim",
    "get_stim_artifact_duration",
    "get_fr_aligned_to_stim",
    "stim_activity_analysis",
    "write_stim_activity_csv",
    "CSV_COLUMNS",
    "compute_reservoir_matrices",
    "stim_shuffle_test",
    "compute_trial_proportion",
    "plot_stim_times",
    "plot_stim_heatmap",
    "plot_stim_heatmap_w_metric",
    "plot_idv_stim_data_and_trace",
    "plot_stim_detection_checks",
    "plot_pre_post_stim_fr",
    "plot_metric_aligned_to_stim",
    "plot_stim_shuffle_results",
    "plot_individual_psth_and_raster",
    "plot_individual_psth_and_raster_for_pattern",
    "values_to_colormap",
    "compute_median_spike_latency",
]
