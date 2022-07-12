# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_files\variable_part_editor.ui'
#
# Created by: PyQt5 UI code generator 5.7
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_VariablePartEditorWidget(object):
    def setupUi(self, VariablePartEditorWidget):
        VariablePartEditorWidget.setObjectName("VariablePartEditorWidget")
        VariablePartEditorWidget.resize(484, 337)
        self.horizontalLayout = QtWidgets.QHBoxLayout(VariablePartEditorWidget)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.variable_data = QtWidgets.QPlainTextEdit(VariablePartEditorWidget)
        self.variable_data.setEnabled(True)
        self.variable_data.setContextMenuPolicy(QtCore.Qt.PreventContextMenu)
        self.variable_data.setPlaceholderText("Valid Python Expression. Example: None, 123 + 456, [1,2,3] or \"a string\" (needs quotes).")
        self.variable_data.setObjectName("variable_data")
        self.horizontalLayout.addWidget(self.variable_data)

        self.retranslateUi(VariablePartEditorWidget)
        QtCore.QMetaObject.connectSlotsByName(VariablePartEditorWidget)

    def retranslateUi(self, VariablePartEditorWidget):
        _translate = QtCore.QCoreApplication.translate
        VariablePartEditorWidget.setWindowTitle(_translate("VariablePartEditorWidget", "Variable Part"))

