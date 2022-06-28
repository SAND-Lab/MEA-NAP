# fig2svg is now unmaintained

Matlab and GNU Octave support SVG files. Unfortunately, Matlab's SVG files do not scale nicely and are restricted to the figure size at the time of saving. You can use [svg_fix_viewbox](https://www.mathworks.com/matlabcentral/fileexchange/49617-svg_fix_viewbox-in_name-varargin) to fix this issue.

----

## Previous Content

### fig2svg toolbox: a Matlab/GNU Octave FIG to SVG converter

fig2svg is a Matlab/GNU Octave toolbox that converts Matlab/GNU Octave figures to Scalable Vector Graphics (SVG). The most important feature when comparing fig2svg to plot2svg is that fig2svg has enhanced compatibility, especially for Matlab graphics > 2014a. Note that plot2svg function is deprecated in the fig2svg toolbox and will be removed in the next major release (keeping it now to ease transitions from plot2svg to fig2svg). Thus, plot2svg use in this toolbox is discouraged. Please use fig2svg instead.

### Updated Features

#### Done:

- bar plot
- scatter plot
- legend
- colorbar
- ticklabelrotation
- annotations
- 3D plots (distinct azimuth values)

#### Limitations:

- horizontal bar plot
- stairs and stem plots
- patch enhancements (issue #10)
- 3D plots (distinct elevation values issue #15)
- your feature request ;-)

#### Credit

fig2svg was originally a fork of [plot2svg](https://github.com/jschwizer99/plot2svg)
