"""Functions to visualize matrices of data."""
import itertools

import colorsys
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import gridspec
import numpy as np
import pandas as pd
from scipy.spatial import distance
from scipy.cluster import hierarchy

from .axisgrid import Grid
from .palettes import cubehelix_palette
from .utils import despine, axis_ticklabels_overlap
from .external.six.moves import range


def _index_to_label(index):
    """Convert a pandas index or multiindex to an axis label."""
    if isinstance(index, pd.MultiIndex):
        return "-".join(map(str, index.names))
    else:
        return index.name


def _index_to_ticklabels(index):
    """Convert a pandas index or multiindex into ticklabels."""
    if isinstance(index, pd.MultiIndex):
        return ["-".join(map(str, i)) for i in index.values]
    else:
        return index.values


def _convert_colors(colors):
    """Convert either a list of colors or nested lists of colors to RGB."""
    to_rgb = mpl.colors.colorConverter.to_rgb
    try:
        to_rgb(colors[0])
        # If this works, there is only one level of colors
        return list(map(to_rgb, colors))
    except ValueError:
        # If we get here, we have nested lists
        return [list(map(to_rgb, l)) for l in colors]


class _HeatMapper(object):
    """Draw a heatmap plot of a matrix with nice labels and colormaps."""

    def __init__(self, data, vmin, vmax, cmap, center, robust, annot, fmt,
                 annot_kws, cbar, cbar_kws,
                 xticklabels=True, yticklabels=True, mask=None):
        """Initialize the plotting object."""
        # We always want to have a DataFrame with semantic information
        # and an ndarray to pass to matplotlib
        if isinstance(data, pd.DataFrame):
            plot_data = data.values
        else:
            plot_data = np.asarray(data)
            data = pd.DataFrame(plot_data)

        # Reverse the rows so the plot looks like the matrix
        plot_data = plot_data[::-1]
        data = data.ix[::-1]
        if mask is not None:
            try:
                mask = mask.ix[::-1]
            except AttributeError:
                mask = mask[::-1]

        plot_data = np.ma.masked_where(mask, plot_data)

        # Get good names for the rows and columns
        if isinstance(xticklabels, bool) and xticklabels:
            self.xticklabels = _index_to_ticklabels(data.columns)
        elif isinstance(xticklabels, bool) and not xticklabels:
            self.xticklabels = ['' for _ in range(data.shape[1])]
        else:
            self.xticklabels = xticklabels

        xlabel = _index_to_label(data.columns)

        if isinstance(yticklabels, bool) and yticklabels:
            self.yticklabels = _index_to_ticklabels(data.index)
        elif isinstance(yticklabels, bool) and not yticklabels:
            self.yticklabels = ['' for _ in range(data.shape[0])]
        else:
            self.yticklabels = yticklabels[::-1]

        ylabel = _index_to_label(data.index)

        # Get good names for the axis labels
        self.xlabel = xlabel if xlabel is not None else ""
        self.ylabel = ylabel if ylabel is not None else ""

        # Determine good default values for the colormapping
        self._determine_cmap_params(plot_data, vmin, vmax,
                                    cmap, center, robust)

        # Save other attributes to the object
        self.data = data
        self.plot_data = plot_data
        self.annot = annot
        self.fmt = fmt
        self.annot_kws = {} if annot_kws is None else annot_kws
        self.cbar = cbar
        self.cbar_kws = {} if cbar_kws is None else cbar_kws

    def _determine_cmap_params(self, plot_data, vmin, vmax,
                               cmap, center, robust):
        """Use some heuristics to set good defaults for colorbar and range."""
        calc_data = plot_data.data[~np.isnan(plot_data.data)]
        if vmin is None:
            vmin = np.percentile(calc_data, 2) if robust else calc_data.min()
        if vmax is None:
            vmax = np.percentile(calc_data, 98) if robust else calc_data.max()

        # Simple heuristics for whether these data should  have a divergent map
        divergent = ((vmin < 0) and (vmax > 0)) or center is not None

        # Now set center to 0 so math below makes sense
        if center is None:
            center = 0

        # A divergent map should be symmetric around the center value
        if divergent:
            vlim = max(abs(vmin - center), abs(vmax - center))
            vmin, vmax = -vlim, vlim
        self.divergent = divergent

        # Now add in the centering value and set the limits
        vmin += center
        vmax += center
        self.vmin = vmin
        self.vmax = vmax

        # Choose default colormaps if not provided
        if cmap is None:
            if divergent:
                self.cmap = "RdBu_r"
            else:
                self.cmap = cubehelix_palette(light=.95, as_cmap=True)
        else:
            self.cmap = cmap

    def _annotate_heatmap(self, ax, mesh):
        """Add textual labels with the value in each cell."""
        xpos, ypos = np.meshgrid(ax.get_xticks(), ax.get_yticks())
        for x, y, val, color in zip(xpos.flat, ypos.flat,
                                    mesh.get_array(), mesh.get_facecolors()):
            _, l, _ = colorsys.rgb_to_hls(*color[:3])
            text_color = ".15" if l > .5 else "w"
            val = ("{:" + self.fmt + "}").format(val)
            ax.text(x, y, val, color=text_color,
                    ha="center", va="center", **self.annot_kws)

    def plot(self, ax, cax, kws):
        """Draw the heatmap on the provided Axes."""
        # Remove all the Axes spines
        despine(ax=ax, left=True, bottom=True)

        # Draw the heatmap
        mesh = ax.pcolormesh(self.plot_data, vmin=self.vmin, vmax=self.vmax,
                             cmap=self.cmap, **kws)

        # Set the axis limits
        ax.set(xlim=(0, self.data.shape[1]), ylim=(0, self.data.shape[0]))

        # Add row and column labels
        nx, ny = self.data.T.shape
        ax.set(xticks=np.arange(nx) + .5, yticks=np.arange(ny) + .5)
        xtl = ax.set_xticklabels(self.xticklabels)
        ytl = ax.set_yticklabels(self.yticklabels, rotation="vertical")

        # Possibly rotate them if they overlap
        plt.draw()
        if axis_ticklabels_overlap(xtl):
            plt.setp(xtl, rotation="vertical")
        if axis_ticklabels_overlap(ytl):
            plt.setp(ytl, rotation="horizontal")

        # Add the axis labels
        ax.set(xlabel=self.xlabel, ylabel=self.ylabel)

        # Annotate the cells with the formatted values
        if self.annot:
            self._annotate_heatmap(ax, mesh)

        # Possibly add a colorbar
        if self.cbar:
            ticker = mpl.ticker.MaxNLocator(6)
            cb = ax.figure.colorbar(mesh, cax, ax,
                                    ticks=ticker, **self.cbar_kws)
            cb.outline.set_linewidth(0)


def heatmap(data, vmin=None, vmax=None, cmap=None, center=None, robust=False,
            annot=False, fmt=".2g", annot_kws=None,
            linewidths=.5, linecolor="white",
            cbar=True, cbar_kws=None, cbar_ax=None,
            square=False, ax=None, xticklabels=True, yticklabels=True,
            mask=None,
            **kwargs):
    """Plot rectangular data as a color-encoded matrix.

    This function tries to infer a good colormap to use from the data, but
    this is not guaranteed to work, so take care to make sure the kind of
    colormap (sequential or diverging) and its limits are appropriate.

    This is an Axes-level function and will draw the heatmap into the
    currently-active Axes if none is provided to the ``ax`` argument.  Part of
    this Axes space will be taken and used to plot a colormap, unless ``cbar``
    is False or a separate Axes is provided to ``cbar_ax``.

    Parameters
    ----------
    data : rectangular dataset
        2D dataset that can be coerced into an ndarray. If a Pandas DataFrame
        is provided, the index/column information will be used to label the
        columns and rows.
    vmin, vmax : floats, optional
        Values to anchor the colormap, otherwise they are inferred from the
        data and other keyword arguments. When a diverging dataset is inferred,
        one of these values may be ignored.
    cmap : matplotlib colormap name or object, optional
        The mapping from data values to color space. If not provided, this
        will be either a cubehelix map (if the function infers a sequential
        dataset) or ``RdBu_r`` (if the function infers a diverging dataset).
    center : float, optional
        The value at which to center the colormap. Passing this value implies
        use of a diverging colormap.
    robust : bool, optional
        If True and ``vmin`` or ``vmax`` are absent, the colormap range is
        computed with robust quantiles instead of the extreme values.
    annot : bool, optional
        If True, write the data value in each cell.
    fmt : string, optional
        String formatting code to use when ``annot`` is True.
    annot_kws : dict of key, value mappings, optional
        Keyword arguments for ``ax.text`` when ``annot`` is True.
    linewidths : float, optional
        Width of the lines that divide each cell.
    linecolor : color, optional
        Color of the lines that divide each cell.
    cbar : boolean, optional
        Whether to draw a colorbar.
    cbar_kws : dict of key, value mappings, optional
        Keyword arguments for `fig.colorbar`.
    cbar_ax : matplotlib Axes, optional
        Axes in which to draw the colorbar, otherwise take space from the
        main Axes.
    square : boolean, optional
        If True, set the Axes aspect to "equal" so each cell will be
        square-shaped.
    ax : matplotlib Axes, optional
        Axes in which to draw the plot, otherwise use the currently-active
        Axes.
    xtickabels : list-like or bool, optional
        If True, plot the column names of the dataframe. If False, don't plot
        the column names. If list-like, plot these alternate labels as the
        xticklabels
    yticklabels : list-like or bool, optional
        If True, plot the row names of the dataframe. If False, don't plot
        the row names. If list-like, plot these alternate labels as the
        yticklabels
    mask : boolean numpy.array, optional
        A boolean array indicating where to mask the data so it is not
        plotted on the heatmap. Only used for visualizing, not for calculating.
    kwargs : other keyword arguments
        All other keyword arguments are passed to ``ax.pcolormesh``.

    Returns
    -------
    ax : matplotlib Axes
        Axes object with the heatmap.

    """
    # Initialize the plotter object
    plotter = _HeatMapper(data, vmin, vmax, cmap, center, robust, annot, fmt,
                          annot_kws, cbar, cbar_kws, xticklabels, yticklabels,
                          mask)

    # Add the pcolormesh kwargs here
    kwargs["linewidths"] = linewidths
    kwargs["edgecolor"] = linecolor

    # Draw the plot and return the Axes
    if ax is None:
        ax = plt.gca()
    if square:
        ax.set_aspect("equal")
    plotter.plot(ax, cbar_ax, kwargs)
    return ax


class _DendrogramPlotter(object):
    """Object for drawing tree of similarities between data rows/columns"""

    def __init__(self, data, linkage, metric, method, axis, label, rotate):
        """Plot a dendrogram of the relationships between the columns of data

        Parameters
        ----------
        data : pandas.DataFrame
            Rectangular data
        """
        self.axis = axis
        if self.axis == 1:
            data = data.T

        if isinstance(data, pd.DataFrame):
            array = data.values
        else:
            array = np.asarray(data)
            data = pd.DataFrame(array)

        self.array = array
        self.data = data

        self.shape = self.data.shape
        self.metric = metric
        self.method = method
        self.axis = axis
        self.label = label
        self.rotate = rotate

        if linkage is None:
            self.linkage = self.calculated_linkage
        else:
            self.linkage = linkage
        self.dendrogram = self.calculate_dendrogram()

        # Dendrogram ends are always at multiples of 5, who knows why
        ticks = 10 * np.arange(self.data.shape[0]) + 5

        if self.label:
            ticklabels = _index_to_ticklabels(self.data.index)
            ticklabels = [ticklabels[i] for i in self.reordered_ind]
            if self.rotate:
                self.xticks = []
                self.yticks = ticks
                self.xticklabels = []

                self.yticklabels = ticklabels
                self.ylabel = _index_to_label(self.data.index)
                self.xlabel = ''
            else:
                self.xticks = ticks
                self.yticks = []
                self.xticklabels = ticklabels
                self.yticklabels = []
                self.ylabel = ''
                self.xlabel = _index_to_label(self.data.index)
        else:
            self.xticks, self.yticks = [], []
            self.yticklabels, self.xticklabels = [], []
            self.xlabel, self.ylabel = '', ''

        if self.rotate:
            self.X = self.dendrogram['dcoord']
            self.Y = self.dendrogram['icoord']
        else:
            self.X = self.dendrogram['icoord']
            self.Y = self.dendrogram['dcoord']

    def _calculate_linkage_scipy(self):
        if np.product(self.shape) >= 10000:
            UserWarning('This will be slow... (gentle suggestion: '
                        '"pip install fastcluster")')

        pairwise_dists = distance.squareform(
            distance.pdist(self.array, metric=self.metric))
        linkage = hierarchy.linkage(pairwise_dists, method=self.method)
        del pairwise_dists
        return linkage

    def _calculate_linkage_fastcluster(self):
        import fastcluster
        # Fastcluster has a memory-saving vectorized version, but only
        # with certain linkage methods, and mostly with euclidean metric
        vector_methods = ('single', 'centroid', 'median', 'ward')
        euclidean_methods = ('centroid', 'median', 'ward')
        euclidean = self.metric == 'euclidean' and self.method in \
            euclidean_methods
        if euclidean or self.method == 'single':
            return fastcluster.linkage_vector(self.array,
                                              method=self.method,
                                              metric=self.metric)
        else:
            pairwise_dists = distance.pdist(self.array, metric=self.metric)
            linkage = fastcluster.linkage(pairwise_dists, method=self.method)
            del pairwise_dists
            return linkage

    @property
    def calculated_linkage(self):
        try:
            return self._calculate_linkage_fastcluster()
        except ImportError:
            return self._calculate_linkage_scipy()

    def calculate_dendrogram(self):
        """Calculates a dendrogram based on the linkage matrix

        Made a separate function, not a property because don't want to
        recalculate the dendrogram every time it is accessed.

        Returns
        -------
        dendrogram : dict
            Dendrogram dictionary as returned by scipy.cluster.hierarchy
            .dendrogram. The important key-value pairing is
            "reordered_ind" which indicates the re-ordering of the matrix
        """
        return hierarchy.dendrogram(self.linkage, no_plot=True,
                                    color_list=['k'], color_threshold=-np.inf)

    @property
    def reordered_ind(self):
        """Indices of the matrix, reordered by the dendrogram"""
        return self.dendrogram['leaves']

    def plot(self, ax):
        """Plots a dendrogram of the similarities between data on the axes

        Parameters
        ----------
        ax : matplotlib.axes.Axes
            Axes object upon which the dendrogram is plotted

        """
        for x, y in zip(self.X, self.Y):
            ax.plot(x, y, color='k', linewidth=.5)

        if self.rotate and self.axis == 0:
            ax.invert_xaxis()
            ax.yaxis.set_ticks_position('right')

            ymax = min(map(min, self.Y)) + max(map(max, self.Y))
            ax.set_ylim(0, ymax)
            ax.invert_yaxis()
        else:
            xmax = min(map(min, self.X)) + max(map(max, self.X))
            ax.set_xlim(0, xmax)

        despine(ax=ax, bottom=True, left=True)

        ax.set(xticks=self.xticks, yticks=self.yticks,
               xlabel=self.xlabel, ylabel=self.ylabel)
        xtl = ax.set_xticklabels(self.xticklabels)
        ytl = ax.set_yticklabels(self.yticklabels, rotation='vertical')

        # Force a draw of the plot to avoid matplotlib window error
        plt.draw()
        if len(ytl) > 0 and axis_ticklabels_overlap(ytl):
            plt.setp(ytl, rotation="horizontal")
        if len(xtl) > 0 and axis_ticklabels_overlap(xtl):
            plt.setp(xtl, rotation="vertical")
        return self


def dendrogram(data, linkage=None, axis=1, label=True, metric='euclidean',
               method='average', rotate=False, ax=None):
    """Draw a tree diagram of relationships within a matrix

    Parameters
    ----------
    data : pandas.DataFrame
        Rectangular data
    linkage : numpy.array, optional
        Linkage matrix
    axis : int, optional
        Which axis to use to calculate linkage. 0 is rows, 1 is columns.
    label : bool, optional
        If True, label the dendrogram at leaves with column or row names
    metric : str, optional
        Distance metric. Anything valid for scipy.spatial.distance.pdist
    method : str, optional
        Linkage method to use. Anything valid for
        scipy.cluster.hierarchy.linkage
    rotate : bool, optional
        When plotting the matrix, whether to rotate it 90 degrees
        counter-clockwise, so the leaves face right
    ax : matplotlib axis, optional
        Axis to plot on, otherwise uses current axis

    Returns
    -------
    dendrogramplotter : _DendrogramPlotter
        A Dendrogram plotter object.

    Notes
    -----
    Access the reordered dendrogram indices with
    dendrogramplotter.reordered_ind

    """
    plotter = _DendrogramPlotter(data, linkage=linkage, axis=axis,
                                 metric=metric, method=method,
                                 label=label, rotate=rotate)
    if ax is None:
        ax = plt.gca()
    return plotter.plot(ax=ax)


class ClusterGrid(Grid):
    def __init__(self, data, pivot_kws=None, z_score=None, standard_scale=None,
                 figsize=None, row_colors=None, col_colors=None):
        """Grid object for organizing clustered heatmap input on to axes"""

        if isinstance(data, pd.DataFrame):
            self.data = data
        else:
            self.data = pd.DataFrame(data)

        self.data2d = self.format_data(self.data, pivot_kws, z_score,
                                       standard_scale)

        if figsize is None:
            width, height = 10, 10
            figsize = (width, height)
        self.fig = plt.figure(figsize=figsize)

        if row_colors is not None:
            row_colors = _convert_colors(row_colors)
        self.row_colors = row_colors
        if col_colors is not None:
            col_colors = _convert_colors(col_colors)
        self.col_colors = col_colors

        width_ratios = self.dim_ratios(self.row_colors,
                                       figsize=figsize,
                                       axis=1)

        height_ratios = self.dim_ratios(self.col_colors,
                                        figsize=figsize,
                                        axis=0)
        nrows = 3 if self.col_colors is None else 4
        ncols = 3 if self.row_colors is None else 4

        self.gs = gridspec.GridSpec(nrows, ncols, wspace=0.01, hspace=0.01,
                                    width_ratios=width_ratios,
                                    height_ratios=height_ratios)

        self.ax_row_dendrogram = self.fig.add_subplot(self.gs[nrows - 1, 0:2],
                                                      axisbg="white")
        self.ax_col_dendrogram = self.fig.add_subplot(self.gs[0:2, ncols - 1],
                                                      axisbg="white")

        self.ax_row_colors = None
        self.ax_col_colors = None

        if self.row_colors is not None:
            self.ax_row_colors = self.fig.add_subplot(
                self.gs[nrows - 1, ncols - 2])
        if self.col_colors is not None:
            self.ax_col_colors = self.fig.add_subplot(
                self.gs[nrows - 2, ncols - 1])

        self.ax_heatmap = self.fig.add_subplot(self.gs[nrows - 1, ncols - 1])

        # colorbar for scale to left corner
        self.cax = self.fig.add_subplot(self.gs[0, 0])

        self.dendrogram_row = None
        self.dendrogram_col = None

    def format_data(self, data, pivot_kws, z_score=None,
                    standard_scale=None):
        """Extract variables from data or use directly."""

        # Either the data is already in 2d matrix format, or need to do a pivot
        if pivot_kws is not None:
            data2d = data.pivot(**pivot_kws)
        else:
            data2d = data

        if z_score is not None and standard_scale is not None:
            raise ValueError(
                'Cannot perform both z-scoring and standard-scaling on data')

        if z_score is not None:
            data2d = self.z_score(data2d, z_score)
        if standard_scale is not None:
            data2d = self.standard_scale(data2d, standard_scale)
        return data2d

    @staticmethod
    def z_score(data2d, axis=1):
        """Standarize the mean and variance of the data axis

        Parameters
        ----------
        data2d : pandas.DataFrame
            Data to normalize
        axis : int
            Which axis to normalize across. If 0, normalize across rows, if 1,
            normalize across columns.

        Returns
        -------
        normalized : pandas.DataFrame
            Noramlized data with a mean of 0 and variance of 1 across the
            specified axis.
        """
        if axis == 1:
            z_scored = data2d
        else:
            z_scored = data2d.T

        z_scored = (z_scored - z_scored.mean()) / z_scored.var()

        if axis == 1:
            return z_scored
        else:
            return z_scored.T

    @staticmethod
    def standard_scale(data2d, axis=1):
        """Divide the data by the difference between the max and min

        Parameters
        ----------
        data2d : pandas.DataFrame
            Data to normalize
        axis : int
            Which axis to normalize across. If 0, normalize across rows, if 1,
            normalize across columns.
        vmin : int
            If 0, then subtract the minimum of the data before dividing by
            the range.

        Returns
        -------
        standardized : pandas.DataFrame
            Noramlized data with a mean of 0 and variance of 1 across the
            specified axis.

        >>> import numpy as np
        >>> d = np.arange(5, 8, 0.5)
        >>> ClusterGrid.standard_scale(d)
        array([ 0. ,  0.2,  0.4,  0.6,  0.8,  1. ])
        """
        # Normalize these values to range from 0 to 1
        if axis == 1:
            standardized = data2d
        else:
            standardized = data2d.T

        subtract = standardized.min()
        standardized = (standardized - subtract) / (
            standardized.max() - standardized.min())

        if axis == 1:
            return standardized
        else:
            return standardized.T

    def dim_ratios(self, side_colors, axis, figsize, side_colors_ratio=0.05):
        """Get the proportions of the figure taken up by each axes
        """
        figdim = figsize[axis]
        # Get resizing proportion of this figure for the dendrogram and
        # colorbar, so only the heatmap gets bigger but the dendrogram stays
        # the same size.
        dendrogram = min(2. / figdim, .2)

        # add the colorbar
        colorbar_width = .8 * dendrogram
        colorbar_height = .2 * dendrogram
        if axis == 0:
            ratios = [colorbar_width, colorbar_height]
        else:
            ratios = [colorbar_height, colorbar_width]

        if side_colors is not None:
            # Add room for the colors
            ratios += [side_colors_ratio]

        # Add the ratio for the heatmap itself
        ratios += [.8]

        return ratios

    @staticmethod
    def color_list_to_matrix_and_cmap(colors, ind, axis=0):
        """Turns a list of colors into a numpy matrix and matplotlib colormap

        These arguments can now be plotted using heatmap(matrix, cmap)
        and the provided colors will be plotted.

        Parameters
        ----------
        colors : list of matplotlib colors
            Colors to label the rows or columns of a dataframe.
        ind : list of ints
            Ordering of the rows or columns, to reorder the original colors
            by the clustered dendrogram order
        axis : int
            Which axis this is labeling

        Returns
        -------
        matrix : numpy.array
            A numpy array of integer values, where each corresponds to a color
            from the originally provided list of colors
        cmap : matplotlib.colors.ListedColormap

        """
        # check for nested lists/color palettes.
        # Will fail if matplotlib color is list not tuple
        if any(issubclass(type(x), list) for x in colors):
            all_colors = set(itertools.chain(*colors))
            n = len(colors)
            m = len(colors[0])
        else:
            all_colors = set(colors)
            n = 1
            m = len(colors)
            colors = [colors]
        color_to_value = dict((col, i) for i, col in enumerate(all_colors))

        matrix = np.array([color_to_value[c]
                           for color in colors for c in color])

        shape = (n, m)
        matrix = matrix.reshape(shape)
        matrix = matrix[:, ind]
        if axis == 0:
            # row-side:
            matrix = matrix.T

        cmap = mpl.colors.ListedColormap(all_colors)
        return matrix, cmap

    def savefig(self, *args, **kwargs):
        if 'bbox_inches' not in kwargs:
            kwargs['bbox_inches'] = 'tight'
        self.fig.savefig(*args, **kwargs)

    def plot_dendrograms(self, row_cluster, col_cluster, metric, method,
                         row_linkage, col_linkage):
        # Plot the row dendrogram
        if row_cluster:
            self.dendrogram_row = dendrogram(
                self.data2d, metric=metric, method=method, label=False, axis=0,
                ax=self.ax_row_dendrogram, rotate=True, linkage=row_linkage)
        else:
            self.ax_row_dendrogram.set_xticks([])
            self.ax_row_dendrogram.set_yticks([])
        # PLot the column dendrogram
        if col_cluster:
            self.dendrogram_col = dendrogram(
                self.data2d, metric=metric, method=method, label=False,
                axis=1, ax=self.ax_col_dendrogram, linkage=col_linkage)
        else:
            self.ax_col_dendrogram.set_xticks([])
            self.ax_col_dendrogram.set_yticks([])
        despine(ax=self.ax_row_dendrogram, bottom=True, left=True)
        despine(ax=self.ax_col_dendrogram, bottom=True, left=True)

    def plot_colors(self, xind, yind, **kws):
        """Plots color labels between the dendrogram and the heatmap

        Parameters
        ----------
        heatmap_kws : dict
            Keyword arguments heatmap
        """
        # Remove any custom colormap and centering
        kws = kws.copy()
        kws.pop('cmap', None)
        kws.pop('center', None)
        if self.row_colors is not None:
            matrix, cmap = self.color_list_to_matrix_and_cmap(
                self.row_colors, yind, axis=0)
            heatmap(matrix, cmap=cmap, cbar=False, ax=self.ax_row_colors,
                    xticklabels=False, yticklabels=False,
                    **kws)
        else:
            despine(self.ax_row_colors, left=True, bottom=True)

        if self.col_colors is not None:
            matrix, cmap = self.color_list_to_matrix_and_cmap(
                self.col_colors, xind, axis=1)
            heatmap(matrix, cmap=cmap, cbar=False, ax=self.ax_col_colors,
                    xticklabels=False, yticklabels=False,
                    **kws)
        else:
            despine(self.ax_col_colors, left=True, bottom=True)

    def plot_matrix(self, colorbar_kws, mask, xind, yind, **kws):
        self.data2d = self.data2d.iloc[yind, xind]
        heatmap(self.data2d, ax=self.ax_heatmap, cbar_ax=self.cax,
                cbar_kws=colorbar_kws, mask=mask, **kws)
        self.ax_heatmap.yaxis.set_ticks_position('right')
        self.ax_heatmap.yaxis.set_label_position('right')

    def plot(self, metric, method, colorbar_kws, row_cluster, col_cluster,
             row_linkage, col_linkage, mask, **kws):
        colorbar_kws = {} if colorbar_kws is None else colorbar_kws
        self.plot_dendrograms(row_cluster, col_cluster, metric, method,
                              row_linkage=row_linkage, col_linkage=col_linkage)
        try:
            xind = self.dendrogram_col.reordered_ind
        except AttributeError:
            xind = np.arange(self.data2d.shape[1])
        try:
            yind = self.dendrogram_row.reordered_ind
        except AttributeError:
            yind = np.arange(self.data2d.shape[0])

        self.plot_colors(xind, yind, **kws)
        self.plot_matrix(colorbar_kws, mask, xind, yind, **kws)
        return self


def clustermap(data, pivot_kws=None, method='average', metric='euclidean',
               z_score=None, standard_scale=None, figsize=None, cbar_kws=None,
               row_cluster=True, col_cluster=True,
               row_linkage=None, col_linkage=None,
               row_colors=None, col_colors=None, mask=None, **kwargs):
    """Plot a hierarchically clustered heatmap of a pandas DataFrame

    Parameters
    ----------
    data: pandas.DataFrame
        Rectangular data for clustering. Cannot contain NAs.
    pivot_kws : dict, optional
        If `data` is a tidy dataframe, can provide keyword arguments for
        pivot to create a rectangular dataframe.
    method : str, optional
        Linkage method to use for calculating clusters.
        See scipy.cluster.hierarchy.linkage documentation for more information:
        http://docs.scipy.org/doc/scipy/reference/generated/scipy.cluster.hierarchy.linkage.html
    metric : str, optional
        Distance metric to use for the data. See
        scipy.spatial.distance.pdist documentation for more options
        http://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.pdist.html
    z_score : int or None, optional
        Either 0 (rows) or 1 (columns). Whether or not to calculate z-scores
        for the rows or the columns. Z scores are: z = (x - mean)/std, so
        values in each row (column) will get the mean of the row (column)
        subtracted, then divided by the standard deviation of the row (column).
        This ensures that each row (column) has mean of 0 and variance of 1.
    standard_scale : int or None, optional
        Either 0 (rows) or 1 (columns). Whether or not to standardize that
        dimension, meaning for each row or column, subtract the minimum and
        divide each by its maximum.
    figsize: tuple of two ints, optional
        Size of the figure to create.
    cbar_kws : dict, optional
        Keyword arguments to pass to ``cbar_kws`` in ``heatmap``, e.g. to
        add a label to the colorbar.
    {row,col}_cluster : bool, optional
        If True, cluster the {rows, columns}.
    {row,col}_linkage : numpy.array, optional
        Precomputed linkage matrix for the rows or columns. See
        scipy.cluster.hierarchy.linkage for specific formats.
    {row,col}_colors : list-like, optional
        List of colors to label for either the rows or columns. Useful to
        evaluate whether samples within a group are clustered together. Can
        use nested lists for multiple color levels of labeling.
    mask : boolean numpy.array, optional
        A boolean array indicating where to mask the data so it is not
        plotted on the heatmap. Only used for visualizing, not for calculating.
    kwargs : other keyword arguments
        All other keyword arguments are passed to ``sns.heatmap``

    Returns
    -------
    clustergrid : ClusterGrid
        A ClusterGrid instance.

    Notes
    ----
    The returned object has a ``savefig`` method that should be used if you
    want to save the figure object without clipping the dendrograms.

    To access the reordered row indices, use:
    ``clustergrid.dendrogram_row.reordered_ind``

    Column indices, use:
    ``clustergrid.dendrogram_col.reordered_ind``

    """
    plotter = ClusterGrid(data, pivot_kws=pivot_kws, figsize=figsize,
                          row_colors=row_colors, col_colors=col_colors,
                          z_score=z_score, standard_scale=standard_scale)

    return plotter.plot(metric=metric, method=method,
                        colorbar_kws=cbar_kws,
                        row_cluster=row_cluster, col_cluster=col_cluster,
                        row_linkage=row_linkage, col_linkage=col_linkage,
                        mask=mask,
                        **kwargs)
