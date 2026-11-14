---
key: NMF
name: NMF components
also: num_nnmf_components, nComponentsRelNS
level: recording
family: network
related: effRank, aN, nMod
---
How many recurring patterns of co-active electrodes are needed to describe the recording, found with non-negative matrix factorisation (NMF).

## What it measures

NMF breaks the binned spike counts into a small number of components. Each component is a group of electrodes that tend to fire together, plus a time course for when that group is active. The number of components that capture real structure, rather than chance coincidences, is a measure of how many distinct assemblies or activity patterns the culture expresses.

- **num_nnmf_components**: the number of components.
- **nComponentsRelNS**: that number divided by the number of electrodes that fired, so recordings with different numbers of active channels can be compared.

## Reading the values

- num_nnmf_components is a whole number from 1 up to the number of channels. nComponentsRelNS is a fraction, usually between 0 and 1.
- **Few components** (low nComponentsRelNS) means a few shared patterns dominate, as when most electrodes join the same network bursts. **More** means more independent or varied assemblies.
- Like effective rank, this describes the activity, not the thresholded network.

## How MEA-NAP calculates it

`cal_nmf` (`meanap.pipeline.nmf`), called once per recording from `_step4_compute_one` (`meanap.pipeline.step4`):

1. Bin every channel's spikes into counts at `{{param:nmf_downsample_freq}}` Hz.
2. Make a shuffled copy in which each channel's spike train is wrapped around a random cut point. This keeps each channel's firing but breaks timing between channels.
3. Fit NMF (scikit-learn, coordinate descent) at rank 1, 2, 3 … to both the real and shuffled matrices. Stop at the first rank where the real data's reconstruction error is no longer smaller than the shuffled data's. That rank is **num_nnmf_components**.
4. **nComponentsRelNS** = num_nnmf_components ÷ the number of channels with more than one spike.

A further sweep records the variance explained at each rank (stopping early according to `{{param:nmf_plateau_gain}}`), but this does not change the two numbers above. NMF can be switched off with `{{param:compute_nmf}}`.

## Things to watch for

- The count does not depend on the STTC lag. It is the same in every lag folder.
- The fits and the shuffle are random, so counts can differ by one between runs. Set `{{param:random_seed}}` for reproducible results.
- MATLAB MEA-NAP uses a different NMF solver, so its counts can differ from Python's.
- The denominator of nComponentsRelNS counts channels that fired, not active network nodes (aN).

## References

- Lee DD, Seung HS (1999) Nature 401:788–791. doi:10.1038/44565
- Sit TPH et al. (2024) Cell Reports Methods 4:100901. doi:10.1016/j.crmeth.2024.100901
