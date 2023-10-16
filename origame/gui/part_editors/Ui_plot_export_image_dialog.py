# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\origame\gui\part_editors\ui_files\plot_export_image_dialog.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_PlotExportImageDialog(object):
    def setupUi(self, PlotExportImageDialog):
        PlotExportImageDialog.setObjectName("PlotExportImageDialog")
        PlotExportImageDialog.resize(378, 143)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(PlotExportImageDialog.sizePolicy().hasHeightForWidth())
        PlotExportImageDialog.setSizePolicy(sizePolicy)
        self.verticalLayout = QtWidgets.QVBoxLayout(PlotExportImageDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.formLayout = QtWidgets.QFormLayout()
        self.formLayout.setObjectName("formLayout")
        self.label_2 = QtWidgets.QLabel(PlotExportImageDialog)
        self.label_2.setToolTip("")
        self.label_2.setObjectName("label_2")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label_2)
        self.image_path_line_edit = QtWidgets.QLineEdit(PlotExportImageDialog)
        self.image_path_line_edit.setText("")
        self.image_path_line_edit.setObjectName("image_path_line_edit")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.image_path_line_edit)
        self.label_3 = QtWidgets.QLabel(PlotExportImageDialog)
        self.label_3.setToolTip("")
        self.label_3.setObjectName("label_3")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.label_3)
        self.label = QtWidgets.QLabel(PlotExportImageDialog)
        self.label.setObjectName("label")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.label)
        self.resolution_combobox = QtWidgets.QComboBox(PlotExportImageDialog)
        self.resolution_combobox.setEditable(True)
        self.resolution_combobox.setObjectName("resolution_combobox")
        self.resolution_combobox.addItem("")
        self.resolution_combobox.addItem("")
        self.resolution_combobox.addItem("")
        self.resolution_combobox.addItem("")
        self.resolution_combobox.addItem("")
        self.resolution_combobox.addItem("")
        self.resolution_combobox.addItem("")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.resolution_combobox)
        self.format_combobox = QtWidgets.QComboBox(PlotExportImageDialog)
        self.format_combobox.setEditable(True)
        self.format_combobox.setObjectName("format_combobox")
        self.format_combobox.addItem("")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.FieldRole, self.format_combobox)
        self.verticalLayout.addLayout(self.formLayout)
        spacerItem = QtWidgets.QSpacerItem(20, 5, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)
        self.button_box = QtWidgets.QDialogButtonBox(PlotExportImageDialog)
        self.button_box.setOrientation(QtCore.Qt.Horizontal)
        self.button_box.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.button_box.setObjectName("button_box")
        self.verticalLayout.addWidget(self.button_box)

        self.retranslateUi(PlotExportImageDialog)
        self.button_box.accepted.connect(PlotExportImageDialog.accept) # type: ignore
        self.button_box.rejected.connect(PlotExportImageDialog.reject) # type: ignore
        QtCore.QMetaObject.connectSlotsByName(PlotExportImageDialog)

    def retranslateUi(self, PlotExportImageDialog):
        _translate = QtCore.QCoreApplication.translate
        PlotExportImageDialog.setWindowTitle(_translate("PlotExportImageDialog", "Export Image"))
        self.label_2.setText(_translate("PlotExportImageDialog", "Image File Path:"))
        self.image_path_line_edit.setPlaceholderText(_translate("PlotExportImageDialog", "Example: C:\\My Pictures\\Origame Plots\\myplot.png"))
        self.label_3.setText(_translate("PlotExportImageDialog", "Resolution (dpi):"))
        self.label.setText(_translate("PlotExportImageDialog", "Format:"))
        self.resolution_combobox.setItemText(0, _translate("PlotExportImageDialog", "100"))
        self.resolution_combobox.setItemText(1, _translate("PlotExportImageDialog", "200"))
        self.resolution_combobox.setItemText(2, _translate("PlotExportImageDialog", "300"))
        self.resolution_combobox.setItemText(3, _translate("PlotExportImageDialog", "500"))
        self.resolution_combobox.setItemText(4, _translate("PlotExportImageDialog", "800"))
        self.resolution_combobox.setItemText(5, _translate("PlotExportImageDialog", "1000"))
        self.resolution_combobox.setItemText(6, _translate("PlotExportImageDialog", "2000"))
        self.format_combobox.setItemText(0, _translate("PlotExportImageDialog", "PNG"))

