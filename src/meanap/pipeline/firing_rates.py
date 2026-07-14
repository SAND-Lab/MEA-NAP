import numpy as np

from meanap.params import Params
from meanap.pipeline.burst_detection import burst_detect_network, single_channel_burst_detection


def firing_rates_bursts(
    spike_times_dict: dict[int, np.ndarray],
    n_channels: int,
    fs: float,
    duration_s: float,
    params: Params
) -> dict:
    """Calculate firing rates and detect bursts matching firingRatesBursts.m."""
    
    # ── 1. Firing Rates ──
    firing_rates = np.zeros(n_channels)
    
    for ch, times in spike_times_dict.items():
        firing_rates[ch] = len(times) / duration_s
        
    active_mask = firing_rates >= params.min_activity_level
    active_fr = firing_rates[active_mask]
    
    fr_active_full = np.full(n_channels, np.nan)
    fr_active_full[active_mask] = active_fr
    
    if len(active_fr) > 0:
        fr_mean = np.round(np.mean(active_fr), 3)
        fr_std = np.round(np.std(active_fr, ddof=1), 3)
        fr_sem = np.round(fr_std / np.sqrt(len(active_fr)), 3)
        fr_median = np.round(np.median(active_fr), 3)
        q75, q25 = np.percentile(active_fr, [75, 25])
        fr_iqr = np.round(q75 - q25, 3)
    else:
        fr_mean = 0.0
        fr_std = 0.0
        fr_sem = 0.0
        fr_median = 0.0
        fr_iqr = 0.0
        
    num_active_elec = len(active_fr)
    
    # ── 2. Network burst detection ──
    b_mat, b_times, b_chans, b_info = burst_detect_network(
        spike_times_dict,
        fs,
        min_spikes=params.min_spike_network_burst,
        min_channels=params.min_channel_network_burst,
        isin_th_param=params.bakkum_network_burst_isi_n_threshold
    )
    
    n_bursts = len(b_times)
    
    mean_nbst_length_s = np.nan
    mean_num_chans_involved = np.nan
    mean_isi_within_ms = np.nan
    mean_isi_outside_ms = np.nan
    cv_of_inbi = np.nan
    nburst_rate = 0.0
    frac_in_nburst = np.nan
    
    if n_bursts > 0:
        nb_lengths = (b_times[:, 1] - b_times[:, 0]) / fs
        mean_nbst_length_s = np.mean(nb_lengths)
        chans_involved = [len(c) for c in b_chans]
        mean_num_chans_involved = np.mean(chans_involved)
        
        # Spikes in burst
        sp_in_bst = 0
        mean_isi_w = []
        for i, bm in enumerate(b_mat):
            # bm is dict {ch: times}
            # flattened unique times in burst
            all_b_t = []
            for t in bm.values():
                all_b_t.extend(t)
            all_b_t = np.sort(np.unique(all_b_t))
            sp_in_bst += len(all_b_t)
            
            if len(all_b_t) > 1:
                isi_w = np.mean(np.diff(all_b_t)) * 1000.0
                mean_isi_w.append(isi_w)
                
        if mean_isi_w:
            mean_isi_within_ms = np.mean(mean_isi_w)
            
        # ISI outside
        all_t = []
        for t in spike_times_dict.values():
            all_t.extend(t)
        all_t = np.sort(np.unique(all_t))
        
        if len(all_t) > 1:
            total_spikes = len(all_t)
            # Find times outside bursts
            # This is complex, just approximate or compute exactly?
            # exact:
            in_b_mask = np.zeros(len(all_t), dtype=bool)
            for (t0, t1) in b_times / fs:
                in_b_mask |= (all_t >= t0) & (all_t <= t1)
            out_t = all_t[~in_b_mask]
            if len(out_t) > 1:
                mean_isi_outside_ms = np.mean(np.diff(out_t)) * 1000.0
                
            frac_in_nburst = np.round(sp_in_bst / total_spikes, 3)
            
        nburst_rate = np.round(60 * (n_bursts / duration_s), 3)
        
        if n_bursts > 1:
            ibis = (b_times[1:, 0] - b_times[:-1, 1]) / fs
            cv_of_inbi = np.round(np.std(ibis, ddof=1) / np.mean(ibis), 3)
            
    # ── 3. Single Channel burst detection ──
    sc_burst_data = single_channel_burst_detection(
        spike_times_dict,
        n_channels,
        fs,
        min_spikes=params.single_channel_burst_min_spike,
        isi_threshold=params.single_channel_isi_threshold,
        recording_duration_s=duration_s
    )
    
    # ── Compile Ephys Dict ──
    bu = sc_burst_data["bursting_units"]
    
    def pad(arr):
        full_arr = np.full(n_channels, np.nan)
        if len(bu) > 0 and len(arr) == len(bu):
            full_arr[bu] = arr
        return full_arr
    
    ephys = {
        "FR": firing_rates,
        "FRactive": fr_active_full,
        "FRmean": fr_mean,
        "FRstd": fr_std,
        "FRsem": fr_sem,
        "FRmedian": fr_median,
        "FRiqr": fr_iqr,
        "numActiveElec": num_active_elec,
        
        "meanNBstLengthS": mean_nbst_length_s,
        "numNbursts": n_bursts,
        "meanNumChansInvolvedInNbursts": mean_num_chans_involved,
        "meanISIWithinNbursts_ms": mean_isi_within_ms,
        "meanISIoutsideNbursts_ms": mean_isi_outside_ms,
        "CVofINBI": cv_of_inbi,
        "NBurstRate": nburst_rate,
        "fracInNburst": frac_in_nburst,
        "burstTimes": b_times / fs,  # in seconds
        
        "burstDetectionInfo": b_info,
        
        "channelBurstingUnits": bu,
        "channelAveBurstRate": sc_burst_data["array_burstRate"],
        "channelBurstRate": pad(sc_burst_data["all_burstRates"]),
        "channelWithinBurstFr": pad(sc_burst_data["all_inBurstFRs"]),
        "channelBurstDur": pad(sc_burst_data["all_burstDurs"]),
        "channelAveBurstDur": sc_burst_data["array_burstDur"],
        "channelISIwithinBurst": pad(sc_burst_data["all_ISIs_within"]),
        "channelAveISIwithinBurst": sc_burst_data["array_ISI_within"],
        "channeISIoutsideBurst": pad(sc_burst_data["all_ISIs_outside"]),
        "channelAveISIoutsideBurst": sc_burst_data["array_ISI_outside"],
        "channelFracSpikesInBursts": pad(sc_burst_data["all_fracsInBursts"]),
        "channelAveFracSpikesInBursts": sc_burst_data["array_fracInBursts"],
    }
    
    return ephys
