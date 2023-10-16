# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Provide scenario plot part functionality

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import Enum
from textwrap import dedent

# [2. third-party]
import matplotlib

if matplotlib.get_backend() not in ('Qt5Agg', 'Agg'):
    # if not setup for Qt or window-less, do it here:
    matplotlib.use('Agg')
from matplotlib import pyplot
from matplotlib.patches import Rectangle, Wedge

import numpy
import xlwt

# [3. local]
from ...core import override, BridgeEmitter, BridgeSignal
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations

from ..part_execs import PyScriptExec, PyScriptFuncCallError
from ..part_execs import PyScenarioImportsManager
from ..ori import IOriSerializable, OriContextEnum, OriScenData, JsonObj
from ..ori import OriPlotPartKeys as PpKeys, OriCommonPartKeys as CpKeys
from ..alerts import ScenAlertLevelEnum, IScenAlertSource
from ..proto_compat_warn import prototype_compat_method, prototype_compat_method_alias

from .base_part import BasePart
from .actor_part import ActorPart
from .common import Position
from .part_types_info import register_new_part_type
from .common import ExcelWriteError
from .part_link import TypeReferencingParts, PartLink, TypeMissingLinkInfo
from .scripted_part import IScriptedPart

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'PlotPart',
    'setup_fig_axes',
    'get_fig_axes',
    'export_fig',
]

log = logging.getLogger('system')

DEFAULT_SCRIPT = """\
def configure():
    axes = setup_axes(2, 1)

    axes[0].set_ylabel('y values')
    axes[0].set_title('x vs y')

    axes[1].set_xlabel('x values')

def plot():
    axes[0].plot([1, 2, 3, 4])

    x = numpy.linspace(0, 1)
    y = numpy.sin(4 * numpy.pi * x) * numpy.exp(-5 * x)
    axes[1].plot(x, y, 'r')
"""

BLANK_SCRIPT = """\
def configure():
    axes = setup_axes()

def plot():
    pass
"""

DEFAULT_FIG_WIDTH_IN = 6.2685  # inches
DEFAULT_FIG_HEIGHT_IN = 6.2685  # inches
DEFAULT_FIG_SIZE = (DEFAULT_FIG_WIDTH_IN, DEFAULT_FIG_HEIGHT_IN)


# -- Function definitions -----------------------------------------------------------------------

class FigMissingAxesError(Exception):
    pass


OneOrMoreAxes = Either[pyplot.Axes, List[pyplot.Axes]]


def setup_fig_axes(fig: pyplot.Figure, rows: int = 1, cols: int = 1, grid: bool = True) -> OneOrMoreAxes:
    """
    Create rows x cols axes (subplots). For default (rows = 1 and cols = 1), returns the (one and only) Axes
    instance itself; else, returns the list of axes of the figure.

    :param fig: the Figure object to setup
    :param rows: number of subplot rows in Figure
    :param cols: number of subplot columns in Figure
    :param grid: True if grid should be shown for all axes; False if no grids shown by default
    """
    fig.clear()

    if rows == 1 and cols == 1:
        axes = fig.add_subplot(1, 1, 1)
        axes.grid(grid)

    else:
        fig_num = 1
        for i in range(rows):
            for j in range(cols):
                axes = fig.add_subplot(rows, cols, fig_num)
                axes.grid(grid)
                fig_num += 1

    return get_fig_axes(fig)


def get_fig_axes(fig: pyplot.Figure) -> OneOrMoreAxes:
    """
    If fig has only one Axes instance, return it; else, returns the list of Axes instances of the figure.
    :param fig: the figure from which to get the axes
    :raise FigMissingAxesError: if figure has not been configured with axes yet (configure() function of script not called
        yet, or setup_axes() not called from configure())
    """
    axes = fig.get_axes()
    if len(axes) < 1:
        raise FigMissingAxesError()

    if len(axes) == 1:
        return axes[0]
    else:
        return axes


def export_fig(fig: pyplot.Figure, filepath: str, dpi: int = 200, file_format: str = None):
    """
    Export a snapshot of the figure. If the figure does not have a canvas, a temporary one is assigned to it.
    :param fig: the matplotlib Figure object to export
    :param filepath: the path of file to export to (will be overwritten if it exists); it can be any type of object
        supported by matplotlib.Figure.savefig(filepath, ...), not just string. Example: if filepath is actually
        an io.StringIO, the caller could call filepath.getvalue() upon return in order to get to the raw pixel data.
    :param dpi: dots-per-inch for export
    :param file_format: one of the formats understood by matplotlib; default format as per matplotlib.Figure.savefig().
    """
    if file_format is not None:
        file_format = file_format.lower()

    # console variant (and tests, typically) will not have a canvas, create a temporary one
    tmp_canvas = None
    if fig.canvas is None:
        from matplotlib.backends.backend_agg import FigureCanvas
        tmp_canvas = FigureCanvas(fig)

    log.info("Exporting image to {} file: {}", file_format, filepath)
    fig.savefig(filepath, format=file_format, dpi=dpi)

    if tmp_canvas is not None:
        # then figure did not have a canvas on call to this method, restore figure to that state:
        fig.set_canvas(None)


def transpose_and_write_to_excel(data: List[List[Any]], xls_file: str, xls_sheet: str = None):
    """
    This function creates an Excel file at the specified path, adds a worksheet with the specified name to the
    file, transposes the provided data, and writes it to the new worksheet and saves the file.
    Note: This method differs from the similar one in SheetPart in that it transposes the data list so that each list
    of data becomes a column rather than a row in the spreadsheet.
    :param data: The 2D array of data to be written.
    :param xls_file: The path of the Excel file to be created.
    :param xls_sheet: The name of the worksheet to be added to the file.
    :raises ExcelWriteError: Raised when an error occurs opening or writing to the excel file or worksheet.
    """
    if xls_sheet is None:
        xls_sheet = 'Sheet1'

    try:
        log.info("Writing data to Excel file: {}, sheet: {}", xls_file, xls_sheet)

        wb = xlwt.Workbook()
        sheet = wb.add_sheet(xls_sheet)

        # Each col represents list in the data 'list of lists'
        cols = len(data)
        for col in range(cols):
            # Each row is one value in the column
            # (each col may have a diff number of rows)
            rows = len(data[col])
            for row in range(rows):
                sheet.write(row, col, data[col][row])

        wb.save(xls_file)
    except Exception as exc:
        log.error("write_to_excel() error. File: {}, Sheet: {}. Error: {}", xls_file, xls_sheet, exc)
        raise ExcelWriteError(
            "write_to_excel() error. File: {}, Sheet: {}. Error: {}".format(xls_file, xls_sheet, exc))


def export_data(fig: pyplot.Figure, file_path: str, sheet: str = None) -> bool:
    """
    Export data from the figure to Excel.
    :param fig: The data from this matplotlib Figure object will be exported.
    :param file_path: The path of file to export to (will be overwritten if it exists).
    :param sheet: The name of the worksheet to be added to the file.
    :returns A boolean indicating if the export was successful.
    """
    data = []
    all_axes = fig.get_axes()
    for axes in all_axes:

        # Line graphs
        if len(axes.lines) != 0:

            for line in axes.lines:
                xd = list(line.get_xdata())
                yd = list(line.get_ydata())

                # Convert numpy types to python types
                xp = [xp_item.item() for xp_item in xd]
                yp = [yp_item.item() for yp_item in yd]
                data.append(xp)
                data.append(yp)

        # Scatter plots
        if len(axes.collections) != 0:
            for collection in axes.collections:
                xy = collection.get_offsets()
                num_points = len(xy)
                xd = [xy[x, 0].item() for x in range(0, num_points)]
                yd = [xy[y, 1].item() for y in range(0, num_points)]
                data.append(xd)
                data.append(yd)

        # Histograms, Bar plots, Pie charts
        if len(axes.patches) != 0:

            xd = []
            yd = []
            wedges = []

            for patch in axes.patches:

                # Histograms, Bar plots
                if isinstance(patch, Rectangle):
                    xd.append(patch.get_x())
                    yd.append(patch.get_height())

                # Pie charts
                elif isinstance(patch, Wedge):
                    theta2 = patch.theta2.item()
                    try:
                        theta1 = patch.theta1.item()
                    except AttributeError:
                        theta1 = patch.theta1
                    nvalue = (theta2 - theta1) * (100.0 / 360.0)
                    wedges.append(nvalue)

            if len(xd) != 0:
                data.append(xd)
                data.append(yd)

            if len(wedges) != 0:
                data.append(wedges)

    try:
        if len(data) != 0:
            transpose_and_write_to_excel(data, file_path, sheet)
            return True
        else:
            log.warning(
                "No data found to plot. Current supported plot types include line, scatter (xy), bar, histogram, "
                "and pie plots.")
            return False
    except ExcelWriteError:
        return False


# -- Class Definitions --------------------------------------------------------------------------

class ErrorCatEnum(Enum):
    compile, config_plot, axes, plot = range(4)
    
    
class PlotPart(BasePart, PyScriptExec, IScriptedPart):
    """
    The plot part contains a Python script that configures a matplotlib Figure instance to have one or more
    plots (in matplotlib, aka Axes). The script must contain two functions, and optionally a third:

    - configure(): calls script's setup_axes() and then configures each plot in figure
    - plot(): calls plot functions (plot, hist, scatter, etc) on axes (if figure only has one plot) or axes[n]
        (n=0..N-1 if figure has N subplots)
    - preview(): optional, does same as plot() but with a smaller hardcoded dataset

    If preview() is defined, it will be used in previews by the GUI; else, plot() will be used for that purpose.

    Once a part instance is created, the GUI should call its update_fig() to update the figre with latest data.
    In practice, the GUI would do this at creation time, and when it receives the sig_axes_changed signal from
    the backend. This signal is emitted if a function part script calls the plot part's
    notify_data_changed() method.

    The preview feature of this class is intended to be used by the GUI only, during edits, so the user can
    modify their script and see the changes (the GUI calls get_preview_fig() for this).

    The figure can be exported to file at any time via the export() method.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    class PlotSignals(BridgeEmitter):
        sig_axes_changed = BridgeSignal()
        sig_script_changed = BridgeSignal(str)

    DEFAULT_FACE_COLOR = "white"

    # The default size is tuned to be just big enough to contain the square FigureCanvas without forcing the
    # scroll bars to become visible.
    DEFAULT_VISUAL_SIZE = dict(width=15.0, height=16.2)
    CAN_BE_LINK_SOURCE = True
    PART_TYPE_NAME = "plot"
    DESCRIPTION = """\
        Use this part to display Matplotlib plots.

        A plot part is set with a script that will configure and populate one or more figures
        in the plot with data. The plot script is set from the plot part editor.
        Plot data is typically sourced by the plot script from one or more data-providing parts
        that the plot part is linked to."""

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        BasePart.__init__(self, parent, name=name, position=position)

        if self._shared_scenario_state is None:
            scen_script_imports_mgr = PyScenarioImportsManager()
        else:
            scen_script_imports_mgr = self._shared_scenario_state.scen_script_imports_mgr

        self.signals = self.PlotSignals()

        self.__figure = pyplot.Figure(figsize=DEFAULT_FIG_SIZE, facecolor=PlotPart.DEFAULT_FACE_COLOR, layout="tight")
        self.set_dpi(int(self.__figure.dpi)) # default value by matplotlib
        self.__script_str = None
        self.__clear_data_on_each_plot = True
        self.__plot_update_reqd__possible = False

        # called by PyScriptExec.__init__ at end:
        # self._setup_namespace()

        self.__script_configure_fig = None
        self.__script_update_fig = None
        self.__try_reset_fig = True

        # calls _setup_namespace():
        PyScriptExec.__init__(self, scen_script_imports_mgr)
        self.set_script(DEFAULT_SCRIPT)

    def get_script(self) -> str:
        """Get the script for this plot part"""
        return self.__script_str

    def set_script(self, value: str):
        """Set the script for this plot part"""
        if value == self.__script_str:
            return

        self.__script_str = value
        self.__try_reset_fig = True
        self._update_debuggable_script(self.__script_str)

        if self._anim_mode_shared:
            self.signals.sig_script_changed.emit(value)

    def clear_data_on_update(self, setting: bool = True):
        """
        By default, data is cleared every time the update_fig() is called.
        :param setting: Set this to False for update_fig() to leave previous data in axes. This is mostly useful
            when points need to be added, instead of plotting entirely new data.
        """
        self.__clear_data_on_each_plot = bool(setting)

    @prototype_compat_method
    def clear(self):
        """
        Clears the figure and sets the script to be a do-nothing script. This method is consistent with the
        prototype API and is intended to satisfy prototype scenarios that make use of this function call.
        """
        self.__figure.clear()
        self.__plot_update_reqd__possible = True

    def reset_fig(self, raise_on_fail: bool = True):
        """
        Clear the figure of all plots and rerun the script's configure() function. Does NOT run the
        script's plot() function (this is done by update_fig(). Note: if this method did not successfully run
        already, first compile and execute script. Any exception raised in the script will get trapped and
        put in the part's last_exec_err_info property. No exceptions should escape from this method.
        """
        self._clear_own_alerts(ScenAlertLevelEnum.error, ErrorCatEnum.compile, ErrorCatEnum.config_plot, ErrorCatEnum.axes,  ErrorCatEnum.plot)
        try:
            alert_categ = ErrorCatEnum.compile
            self._check_compile_and_exec()

            self.__figure.clear()
            alert_categ = ErrorCatEnum.config_plot
            self._py_exec(self.__script_configure_fig)
            try:
                axes = get_fig_axes(self.__figure)
            except FigMissingAxesError:
                alert_categ = ErrorCatEnum.config_plot
                raise ValueError("The configure() function must call setup_axes()")

            self.add_to_namespace('axes', axes)
            self.__try_reset_fig = False

        except Exception as exc:
            err_msg = str(exc)
            log.exception(err_msg)
            self._add_alert(ScenAlertLevelEnum.error, alert_categ, err_msg)
            if raise_on_fail:
                raise

    def update_fig(self):
        """
        Refresh the figure plot data. This cause the plot to be updated and the sig_axes_changed to be emitted;
        the GUI should call canvas's draw() when it receives the signal, to see the changes. The GUI should also
        call this once so plot can get initial data, then call draw().

        Note: if the last call to set_script() or reset_fig() did not succeed, then first calls reset_fig() to
        try once more. Any exception raised in the script will get trapped and
        put in the part's last_exec_error_info property. No exceptions should escape from this method.
        """
        self.__figure.set_dpi(self.dpi)

        if self.__try_reset_fig:
            self.reset_fig()
            if self.has_alerts():
                # still didn't succeed, must abandon
                return

        assert not self.has_alerts()

        if self.__clear_data_on_each_plot:
            for axes in self.__figure.get_axes():
                assert hasattr(axes, 'lines')
                assert hasattr(axes, 'patches')
                assert hasattr(axes, 'collections')
                assert hasattr(axes, 'legend_')
                # remove lines
                while len(axes.lines):
                    axes.lines[0].remove()
                # remove patches
                while len(axes.patches):
                    axes.patches[0].remove()
                # remove collections (to clear scatter plots)
                while len(axes.collections):
                    axes.collections[0].remove()
                axes.legend_ = None
                axes.set_prop_cycle(None)  # reset color cycling
                axes.relim()  # axes scaling

        assert not self.has_alerts()

        try:
            self._py_exec(self.__script_update_fig)
            self.__plot_update_reqd__possible = False
            if self._anim_mode_shared:
                self.signals.sig_axes_changed.emit()

        except Exception as exc:
            self._add_alert(ScenAlertLevelEnum.error, ErrorCatEnum.plot, str(exc), path=self.path)
            raise

    def get_axes(self) -> OneOrMoreAxes:
        """
        If self.figure has only one Axes, return it; else, returns the list of axes of the figure.
        """
        self.__plot_update_reqd__possible = True
        return get_fig_axes(self.__figure)

    def get_figure(self) -> pyplot.Figure:
        """Return the pyplot Figure instance for this part"""
        self.__plot_update_reqd__possible = True
        return self.__figure

    def get_dpi(self) -> int:
        """Return the dpi of the pyplot Figure instance for this part"""
        return self.__dpi

    def set_dpi(self, dpi: int):
        """Set the dpi of the pyplot Figure instance for this part"""
        self.__dpi = dpi
        self.__set_min_content_size(self.__dpi)

    def export_fig(self, filepath: str, dpi: int = 200, file_format: str = None):
        """
        Export a snapshot of the part's figure. See documentation for export_fig() in this module (the first
        paramater is this part's Figure object).
        """
        export_fig(self.__figure, filepath, dpi=dpi, file_format=file_format)

    def export_data(self, file_path: str, sheet: str = None) -> bool:
        """
        Export the data in the part's figure. See documentation for export_data() in this module (the first
        paramater is this part's Figure object).
        """
        success = export_data(self.__figure, file_path, sheet)
        return success

    def get_preview_fig(self, script: str) -> pyplot.Figure:
        """
        Get the pyplot.Figure instance to use for previews (called by GUI if showing preview figure). It uses the
        preview() function of the script, or the plot() function if there is no preview.
        :param script: the script to use to generate the figure.
        """
        preview_fig = pyplot.Figure(figsize=DEFAULT_FIG_SIZE, dpi=self.dpi, facecolor=PlotPart.DEFAULT_FACE_COLOR, layout="tight")

        script_namespace = self.get_py_namespace().copy()
        script_namespace['figure'] = preview_fig

        def setup_preview_axes(*args, **kwargs):
            return setup_fig_axes(preview_fig, *args, **kwargs)

        script_namespace['setup_axes'] = setup_preview_axes

        code_obj = compile(dedent(script), '<script>', "exec")
        exec(code_obj, script_namespace)

        script_configure_fig = script_namespace['configure']
        script_configure_fig()
        script_namespace['axes'] = get_fig_axes(preview_fig)

        for axes in preview_fig.get_axes():
            axes.set_aspect('auto')

        script_preview_plot = script_namespace.get('preview', script_namespace.get('plot'))
        script_preview_plot()

        return preview_fig

    @override(BasePart)
    def on_exec_done(self):
        """
        This function causes a signal to be raised for potential plot part update situations that can happen in
        an undetected way because of how they're performed.
        """
        if self.__plot_update_reqd__possible:
            if self._anim_mode_shared:
                self.signals.sig_axes_changed.emit()
        self.__plot_update_reqd__possible = False

    def setup_axes_proto(self, rows: int = 1, cols: int = 1):
        """
        This method is only available for compatibility with prototype's setup_axes.
        NOTE: If __setup_main_axes() was called on the same plot part prior to calling this function, reset_fig()
        must be called prior to calling this function.
        """
        return self.__setup_axes_proto(rows, cols)

    @override(BasePart)
    def on_outgoing_link_removed(self, link: PartLink):
        PyScriptExec.on_outgoing_link_removed(self, link)

    @override(BasePart)
    def on_outgoing_link_renamed(self, old_name: str, new_name: str):
        PyScriptExec.on_outgoing_link_renamed(self, old_name, new_name)

    @override(BasePart)
    def on_link_target_part_changed(self, link: PartLink):
        PyScriptExec.on_link_target_part_changed(self, link)

    # prototype compatibility adjustments:
    setup_axes = prototype_compat_method_alias(setup_axes_proto, 'setup_axes')
    export = prototype_compat_method_alias(export_fig, 'export')

    # --------------------------- instance PUBLIC properties ----------------------------

    script = property(get_script, set_script)
    dpi = property(get_dpi, set_dpi)
    figure = property(get_figure)
    axes = property(get_axes)

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = (script,) + PyScriptExec.META_AUTO_EDITING_API_EXTEND
    META_AUTO_SEARCHING_API_EXTEND = (script,)
    META_AUTO_SCRIPTING_API_EXTEND = (
        script, get_script, set_script,
        figure, reset_fig, get_axes, update_fig, export_fig,
        export_data,
    )

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(PyScriptExec)
    def _setup_namespace(self):
        """
        Adds more objects into the namespace.
        """
        fig_axes = self.get_from_namespace('axes') if self.namespace_has('axes') else None
        super()._setup_namespace()

        if self._shared_scenario_state is not None:
            # sim controller and event queue:
            sim_proxy_ro = self._shared_scenario_state.sim_controller_scripting_proxy_ro
            self.add_to_namespace('sim', sim_proxy_ro)
            self.add_to_namespace('delay', sim_proxy_ro.delay)

        # parts and links create/remove:
        self.add_to_namespace('matplotlib', matplotlib)
        self.add_to_namespace('numpy', numpy)
        self.add_to_namespace('figure', self.__figure)
        self.add_to_namespace('setup_axes', self.__setup_main_axes)
        self.add_to_namespace('clear_data_on_update', self.clear_data_on_update)

        if fig_axes is not None:
            self.add_to_namespace('axes', fig_axes)

    @override(IScenAlertSource)
    def _on_get_ondemand_alerts(self):
        IScriptedPart._on_get_ondemand_alerts(self)

    @override(BasePart)
    def _get_unused_link_info(self, script: str = None) -> List[str]:
        return IScriptedPart._get_unused_link_info(self, script)

    @override(BasePart)
    def _get_missing_link_info(self, script: str = None) -> TypeMissingLinkInfo:
        return IScriptedPart._get_missing_link_info(self, script)

    @override(BasePart)
    def _handle_link_chain_sources(self,
                                   referencing_parts: TypeReferencingParts,
                                   referenced_link_name: str):
        """
        Finds the references to the "referenced_link_name" in the script, and replaces all of them with
        the "new_referenced_link_name", based on the Origame syntax rules.
        """
        self.find(referencing_parts, referenced_link_name)

    @override(BasePart)
    def _handle_link_chain_rename(self,
                                  referencing_parts: TypeReferencingParts,
                                  referenced_link_name: str,
                                  new_referenced_link_name: str):
        """
        Finds the references to the "referenced_link_name" in the script, and replaces all of them with
        the "new_referenced_link_name", based on the Origame syntax rules.
        """
        self.replace(referencing_parts, referenced_link_name, new_referenced_link_name)

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        BasePart._set_from_ori_impl(self, ori_data, context, **kwargs)

        part_content = ori_data[CpKeys.CONTENT]

        dpi = part_content.get(PpKeys.DPI)
        self.set_dpi(dpi)

        script_pieces = part_content.get(PpKeys.SCRIPT)
        if script_pieces:
            # ORI script is a list of lines of code:
            script_str = '\n'.join(script_pieces)
            # Per BasePart._set_from_ori_impl() docstring, set via property.
            try:
                self.set_script(script_str)
            except Exception:
                log.warning('Script for "{}" not executable, needs fixing', self.path)

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        ori_def = BasePart._get_ori_def_impl(self, context, **kwargs)
        func_ori_def = {
            # ORI script is a list of lines of code:
            PpKeys.SCRIPT: self.__script_str.split('\n'),
            PpKeys.DPI: self.__dpi
        }

        ori_def[CpKeys.CONTENT].update(func_ori_def)
        return ori_def

    @override(BasePart)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        BasePart._get_ori_snapshot_local(self, snapshot, snapshot_slow)
        snapshot.update({PpKeys.SCRIPT: hash(self.__script_str)})

    @override(PyScriptExec)
    def _check_compile_and_exec(self):
        """
        Compile and execute the script, and bind to the configure() and plot() functions created by the
        script execution.
        """
        if PyScriptExec._check_compile_and_exec(self):
            self.__script_configure_fig = self.get_from_namespace('configure')
            self.__script_update_fig = self.get_from_namespace('plot')

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __setup_main_axes(self, rows: int = 1, cols: int = 1, grid: bool = True) -> OneOrMoreAxes:
        """Call self.__setup_fig_axes for the main figure. See __setup_fig_axes() for docstring.
        NOTE: If __setup_axes_proto() was called on the same plot part prior to calling this function, reset_fig()
        must be called prior to calling this function.
        """
        return setup_fig_axes(self.__figure, rows=rows, cols=cols, grid=grid)

    def __setup_axes_proto(self, rows: int, cols: int) -> OneOrMoreAxes:
        """
        This method is only available for compatibility with prototype's setup_axes.
        NOTE: If __setup_main_axes() was called on the same plot part prior to calling this function, reset_fig()
        must be called prior to calling this function.
        """
        self.__plot_update_reqd__possible = True
        return setup_fig_axes(self.__figure, rows=rows, cols=cols)

    def __set_min_content_size(self, dpi: int):
        """
        Sets the MIN_CONTENT_SIZE of the plot part depending on the dpi of the plot.
        These values were obtained by observation. Beyond the specifed size for each dpi, the tight layout
        will not be applied by matplot to the plot, thus, the plot will not be displayed properly.
        """
        if dpi == 100:
            self.MIN_CONTENT_SIZE = dict(width=7.5, height=8.5)
        elif dpi == 200:
            self.MIN_CONTENT_SIZE = dict(width=14.0, height=14.0)
        elif dpi == 300:
            self.MIN_CONTENT_SIZE = dict(width=19.5, height=19.5)
        elif dpi == 400:
            self.MIN_CONTENT_SIZE = dict(width=26.0, height=26.0)
        elif dpi == 500:
            self.MIN_CONTENT_SIZE = dict(width=35.5, height=34.5)

register_new_part_type(PlotPart, PpKeys.PART_TYPE_PLOT)
