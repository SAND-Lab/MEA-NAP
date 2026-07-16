import sys, importlib.util
sys.path.insert(0,'src')
spec=importlib.util.spec_from_file_location('rc','parityRun/run_step1_freshcheck.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
p=m.build_params()
p.start_analysis_step=3; p.stop_analysis_step=4
p.recording_workers=1
# functional connectivity params (match parity run)
p.func_con_lag_val=[10,25,50]
p.trunc_rec=False
p.adj_m_type="weighted"
p.prob_thresh_rep_num=200
p.prob_thresh_tail=0.05
p.prob_thresh_plot_checks=True
from meanap.pipeline.runner import run_pipeline
run_pipeline(p, log=print)
print("STEPS34 DONE")
