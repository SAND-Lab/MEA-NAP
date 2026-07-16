"""Fresh step-1-only Python run to check the ExampleTraces uV-scaling fix.

Runs current spike-detection + step-1 plotting on the bundled Axion example
data with potential_difference_unit='V' (the correct unit for this data, which
is stored in volts). Outputs to parityRun/OutputData_FreshCheck.

    python parityRun/run_step1_freshcheck.py
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.params import Params
from meanap.pipeline.runner import run_pipeline


def build_params() -> Params:
    p = Params()
    p.home_dir = str(REPO_ROOT)
    p.raw_data = str(REPO_ROOT / "ExampleData")
    p.spreadsheet_file_name = str(REPO_ROOT / "parityRun" / "exampleData_parity.csv")
    p.spreadsheet_range = "A2:A3"
    p.output_data_folder = str(REPO_ROOT / "parityRun")
    p.output_data_folder_name = "OutputData_FreshCheck"

    p.fs = 12500.0
    p.d_samp_f = 12500.0
    p.potential_difference_unit = "V"       # <-- correct unit for the volts data
    p.channel_layout = "Axion64"

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

    p.start_analysis_step = 1
    p.stop_analysis_step = 1
    return p


if __name__ == "__main__":
    p = build_params()
    run_pipeline(p, log=print)
    print("DONE")
