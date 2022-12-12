import pdb
import os
import glob
import matplotlib.pyplot as plt
import sciplotlib.style as splstyle
import matplotlib as mpl
import natsort
from PIL import Image
import numpy as np


def combine_plots_across_div(recording_div_folders, plot_names=['FiringRateByElectrode.png'], fig=None, axs=None):
    """
    Parameters
    ----------
    recording_div_folders : list
        list of folders each corresponding to a DIV of the same recording
        eg. [MEC_1B_DIV07, MEC_1B_DIV21, ...]
    plot_names : list
    fig : matplotlib figure object (optional)
    axs : matplotlib axes object (optional)

    Returns
    --------
    """

    if type(plot_names) is not list:
        plot_names = [plot_names]

    num_divs = len(recording_div_folders)

    if (fig is None) and (axs is None):
        fig, axs = plt.subplots(len(plot_names), num_divs, sharex=True, sharey=True)
        if len(plot_names) == 1:
            axs = axs.reshape(-1, 1)
        fig.set_size_inches(3 * num_divs, 3)

    for n_plot_name in np.arange(len(plot_names)):

        plot_name = plot_names[n_plot_name]

        for n_div in np.arange(num_divs):

            recording_folder = recording_div_folders[n_div]
            image_path = os.path.join(recording_folder, plot_name)

            if num_divs > 1:
                with Image.open(image_path) as im:
                    axs[n_plot_name, n_div].imshow(im)

                axs[n_plot_name, n_div].spines['left'].set_visible(False)
                axs[n_plot_name, n_div].spines['bottom'].set_visible(False)
                axs[n_plot_name, n_div].set_xticks([])
                axs[n_plot_name, n_div].set_yticks([])

            else:
                with Image.open(image_path) as im:
                    axs[n_plot_name].imshow(im)
                axs[n_plot_name].spines['left'].set_visible(False)
                axs[n_plot_name].spines['bottom'].set_visible(False)
                axs[n_plot_name].set_xticks([])
                axs[n_plot_name].set_yticks([])

    return fig, axs


def main():

    main_folder = '/Users/timothysit/AnalysisPipeline/OutputDataNov182022/2/2A_IndividualNeuronalAnalysis'
    output_figfolder = '/Users/timothysit/AnalysisPipeline/OutputDataNov182022/2/combined_activity_plots'
    # Go through group names
    group_folders = glob.glob(os.path.join(main_folder, '*/'))

    plot_names = ['FiringRateByElectrode.png', 'Heatmap.png']

    for group_folder in group_folders:

        recording_folders = glob.glob(os.path.join(group_folder, '*/'))
        recording_folder_names = [os.path.basename(os.path.normpath(x)) for x in recording_folders]
        recording_names = ['_'.join(x.split('_')[0:-1]) for x in recording_folder_names]
        unique_recordings = np.unique(recording_names)

        for unique_recording in unique_recordings:

            recording_div_folders = glob.glob(os.path.join(group_folder, '*%s*/' % unique_recording))
            recording_div_folders = natsort.natsorted(recording_div_folders)
            fig_name = '%s_combined_plots.png' % unique_recording
            with plt.style.context(splstyle.get_style('nature-reviews')):
                fig, axs = combine_plots_across_div(recording_div_folders,
                                                    plot_names=plot_names, fig=None, axs=None)
                fig_path = os.path.join(output_figfolder, fig_name)
                fig.savefig(fig_path, dpi=900, bbox_inches='tight')

            plt.close(fig)

if __name__ == '__main__':
    main()