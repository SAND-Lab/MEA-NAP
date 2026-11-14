"""Figures drawn by Qt: one renderer for the file and for the screen.

A figure here is two things. A *scene* is plain data — where each mark is and
how large, in what colour, what the legend says — computed from results with no
drawing library involved (:mod:`meanap.native.scene`). A *painter* draws a
scene with ``QPainter`` (:mod:`meanap.native.network_paint`), and the same call
draws it into a PNG, an SVG, a PDF (:mod:`meanap.native.output`) or a widget in
the application. So the file the pipeline saves, the figure the viewer shows
and the figure the viewer exports are one drawing, not three that agree.

The painters use no widgets, so they run in the pipeline's background thread
and in its worker processes, with no display.
"""
