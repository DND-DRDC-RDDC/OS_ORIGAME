# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'origame\gui\part_editors\ui_files\plot_dpi_widget.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_PlotDpiWidget(object):
    def setupUi(self, PlotDpiWidget):
        PlotDpiWidget.setObjectName("PlotDpiWidget")
        self.horizontalLayout = QtWidgets.QVBoxLayout(PlotDpiWidget)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.formLayout = QtWidgets.QFormLayout()
        self.formLayout.setObjectName("formLayout")
        self.resolution_label = QtWidgets.QLabel(PlotDpiWidget)
        self.resolution_label.setObjectName("resolution_label")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.resolution_label)
        self.resolution_combobox = QtWidgets.QComboBox(PlotDpiWidget)
        self.resolution_combobox.setEditable(True)
        self.resolution_combobox.setObjectName("resolution_combobox")
        self.resolution_combobox.addItem("")
        self.resolution_combobox.addItem("")
        self.resolution_combobox.addItem("")
        self.resolution_combobox.addItem("")
        self.resolution_combobox.addItem("")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.resolution_combobox)
        self.horizontalLayout.addLayout(self.formLayout)

        self.retranslateUi(PlotDpiWidget)

    def retranslateUi(self, PlotDpiWidget):
        _translate = QtCore.QCoreApplication.translate
        self.resolution_label.setText(_translate("PlotDpiWidget", "Resolution (dpi):"))
        self.resolution_combobox.setItemText(0, _translate("PlotDpiWidget", "100"))
        self.resolution_combobox.setItemText(1, _translate("PlotDpiWidget", "200"))
        self.resolution_combobox.setItemText(2, _translate("PlotDpiWidget", "300"))
        self.resolution_combobox.setItemText(3, _translate("PlotDpiWidget", "400"))
        self.resolution_combobox.setItemText(4, _translate("PlotDpiWidget", "500"))
