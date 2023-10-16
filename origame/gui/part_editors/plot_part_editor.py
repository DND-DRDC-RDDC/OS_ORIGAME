# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Plot Part Editor.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from pathlib import Path

# [2. third-party]
from PyQt5.QtWidgets import QWidget, QDialog, QMessageBox, QScrollArea
from PyQt5.QtCore import Qt

from matplotlib import pyplot
import matplotlib

if matplotlib.get_backend() != 'Qt5Agg':
    matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvas

# [3. local]
from ...core import override, override_required
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario.defn_parts import PlotPart
from ...scenario import ori
from ..gui_utils import exec_modal_dialog
from ..safe_slot import safe_slot
from ..async_methods import AsyncRequest

from .scenario_part_editor import BaseContentEditor
from .script_editing import PythonScriptEditor
from .part_editors_registry import register_part_editor_class
from .Ui_plot_export_image_dialog import Ui_PlotExportImageDialog
from .Ui_plot_export_data_dialog import Ui_PlotExportDataDialog
from .Ui_plot_dpi_widget import Ui_PlotDpiWidget
from .common import EditorDialog, IPreviewWidget

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'PlotPartEditorPanel',
    'ExportImageDialog',
    'ExportDataDialog'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

# noinspection PyUnresolvedReferences
class PlotEditorDialog(EditorDialog):
    """
    The base class for Plot Editor dialogs sets up the UI features and interface with the plot editor.
    """
    def __init__(self, plot_part: PlotPart, ui: Any, parent: QWidget = None):
        super().__init__(parent)
        self._part = plot_part
        self.ui = ui
        self.ui.setupUi(self)

    @override(QDialog)
    def done(self, result: int):
        if result != QDialog.Rejected:
            isvalid = self.send_to_plot_part()
            if not isvalid:
                # For invalid results, return the user to the orignal dialog to correct mistakes
                return
        super().done(result)

    @override_required
    def send_to_plot_part(self) -> bool:
        """
        Each specific dialog must implement this function to get the dialog information and call the back-end part.
        :return: a boolean indicating if the result is valid.
        """
        raise NotImplementedError('Implementation needed.')


# noinspection PyUnresolvedReferences
class ExportImageDialog(PlotEditorDialog):
    """
    Dialog to export a plot part's figure to an image file.
    """
    def __init__(self, plot_part: PlotPart, plot_widget: QWidget = None):
        ui = Ui_PlotExportImageDialog()
        super().__init__(plot_part, ui, parent=plot_widget)

        self.setWindowTitle('Export Image')

    @override(PlotEditorDialog)
    def send_to_plot_part(self) -> bool:
        """
        Sends the information entered into the dialog to the plot part.
        """
        image_path = self.ui.image_path_line_edit.text()
        image_res = self.ui.resolution_combobox.currentText()
        image_format = self.ui.format_combobox.currentText()

        # Add on extension if left out
        if Path(image_path).suffix == '':
            image_path += '.{}'.format(image_format.lower())

        # Check for errors in user input
        error_found, error_msg = self.__is_error_found(image_path, image_format)

        if error_found:
            msg_title = 'Export Error'
            exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
            log.error('{}: {}', msg_title, error_msg)
            return False

        AsyncRequest.call(self._part.export_fig, image_path, int(image_res), image_format)
        return True

    def __is_error_found(self, image_path: str, image_format: str) -> Tuple[bool, str]:
        """
        Checks for errors in the entered dialog information.
        :param image_path: the path to the image file.
        :param image_format: the format of the image file.
        :returns: a boolean flag that is True if an error was found and a corresponding error message.
        """
        if len(image_path) == 0:
            return True, 'The image path was not specified.'

        if len(image_format) == 0:
            return True, 'The image format was not specified.'

        if not Path(image_path).parent.exists():
            return True, 'The path specified does not exist.'

        return False, str()


# noinspection PyUnresolvedReferences
class ExportDataDialog(PlotEditorDialog):
    """
    Dialog to export a plot part's data to an Excel file.
    """
    def __init__(self, plot_part: PlotPart, plot_widget: QWidget = None):
        ui = Ui_PlotExportDataDialog()
        super().__init__(plot_part, ui, parent=plot_widget)

    @override(PlotEditorDialog)
    def send_to_plot_part(self) -> bool:
        """
        Sends the information entered into the dialog to the plot part.
        """
        file_path = self.ui.file_path_line_edit.text()
        sheet = self.ui.sheet_line_edit.text()
        if sheet == '':
            sheet = 'Sheet1'

        # Check for errors in user input
        error_found, error_msg = self.__is_error_found(file_path)

        if error_found:
            msg_title = 'Export Error'
            exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
            log.error('{}: {}', msg_title, error_msg)
            return False

        # Add on extension if left out
        if Path(file_path).suffix == '':
            file_path += '.xls'

        def on_data_export_complete(success: bool):
            if not success:
                msg_title = 'Export Error'
                warn_msg = 'Plot data export did not succeed. Refer to the log window for more information.'
                exec_modal_dialog(msg_title, warn_msg, QMessageBox.Critical)
                log.warning('{}: {}', msg_title, warn_msg)

        AsyncRequest.call(self._part.export_data, file_path, sheet, response_cb=on_data_export_complete)
        return True

    def __is_error_found(self, file_path: str) -> Tuple[bool, str]:
        """
        Checks for errors in the entered dialog information.
        :param file_path: the path to the Excel file.
        :returns: a boolean flag that is True if an error was found and a corresponding error message.
        """
        if len(file_path) == 0:
            return True, 'The Excel file path was not specified.'

        if not Path(file_path).parent.exists():
            return True, 'The path specified does not exist.'

        return False, str()

class PlotDpiWidget(QWidget):
    """
    Creates the plot resolution setting widget for the plot part editor.
    """
    def __init__(self, current_dpi: int):
        super().__init__()
        self.ui = Ui_PlotDpiWidget()
        self.ui.setupUi(self)
        self.ui.resolution_combobox.setCurrentText(str(current_dpi))

class PlotPreviewWidget(IPreviewWidget):
    """
    Creates the preview panel for the plot part editor.
    """
    def __init__(self, part: PlotPart, set_wait_mode_callback: Callable[[bool], None]):
        super().__init__(set_wait_mode_callback)
        self.__part = part
        self.__canvas = None
        self.script = None

    @override(IPreviewWidget)
    def update(self):
        """
        Draw the plot based on the figure received from the backend.
        """
        assert self.script is not None

        def on_figure_received(figure: pyplot.Figure):
            """
            Method called when an asynchronous call to get the figure for a plot has been received from the
            backend.
            :param figure: An element containing the components of a plot.
            """
            self._set_wait_mode_callback(False)
            self.remove_display_widget()
            self.__canvas.setVisible(False)
            self.__canvas = FigureCanvas(figure)
            self.add_display_widget(self.__canvas)
            fit_in = self.__canvas.size().scaled(self.size(), Qt.KeepAspectRatio)
            self.__canvas.setFixedSize(fit_in * 0.9)

        self._set_wait_mode_callback(True)
        AsyncRequest.call(self.__part.get_preview_fig, self.script, response_cb=on_figure_received)

    def draw_unrefreshed_plot(self, display_text: str):
        """
        On initial load of the Plot Editor, always show the unrefreshed plot figure until the user deliberately clicks
        on the refresh button.
        :param display_text: The text to show in the unrefreshed plot.
        """
        self.remove_display_widget()
        figure = pyplot.Figure(facecolor=PlotPart.DEFAULT_FACE_COLOR)
        figure.text(0.5, 0.5, display_text, horizontalalignment='center', verticalalignment='center')
        figure.add_subplot(1, 1, 1)
        self.__canvas = FigureCanvas(figure)
        self.add_display_widget(self.__canvas)


class PlotPartEditorPanel(PythonScriptEditor):
    """
    Represents the content of the editor under the header of the common Origame editing framework.
    """

    # The initial size to make this editor look nice.
    INIT_WIDTH = 1280
    INIT_HEIGHT = 800
    INIT_PLOT_PREVIEW_WIDTH = 340
    INIT_PLOT_PREVIEW_HEIGHT = 272

    def __init__(self, part: PlotPart, parent: QWidget = None):
        """
        Initialize the plot part editor and add the preview panel.
        :param part: The plot part to edit.
        :param parent: The scenario part editor panel.
        """
        super().__init__(part, parent)
        self.__part = part

        # Add the preview panel
        self.plot_preview_panel = PlotPreviewWidget(part, set_wait_mode_callback=self.set_wait_mode)
        self.plot_preview_panel.ui.update_button.clicked.connect(self.__slot_on_update_button_clicked)
        self.plot_dpi_widget = PlotDpiWidget(current_dpi=part.dpi)
        self.plot_preview_panel.ui.verticalLayout.addWidget(self.plot_dpi_widget)
        self.plot_dpi_widget.ui.resolution_combobox.activated.connect(self.__slot_on_update_button_clicked)
        self.ui.main_code_editor_layout.layout().addWidget(self.plot_preview_panel)

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        This method is used to set part specific content into editors.
        """
        super()._on_data_arrived(data)
        self.ui.code_editor.set_breakpoints(data['breakpoints'])
        self.ui.code_editor.setFocus()
        self.plot_preview_panel.draw_unrefreshed_plot("Unrefreshed Plot")

    def __on_update_button_clicked(self):
        """
        Method called when the update button is clicked within the Plot Part Editor.
        """
        self.plot_preview_panel.draw_unrefreshed_plot("Update pending...")
        self.plot_preview_panel.script = self.ui.code_editor.text()
        self.plot_preview_panel.update()
        self.__part.dpi = int(self.plot_dpi_widget.ui.resolution_combobox.currentText())

    __slot_on_update_button_clicked = safe_slot(__on_update_button_clicked)


register_part_editor_class(ori.OriPlotPartKeys.PART_TYPE_PLOT, PlotPartEditorPanel)
