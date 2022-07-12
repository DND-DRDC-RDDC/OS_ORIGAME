# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_files\sql_part.ui'
#
# Created by: PyQt5 UI code generator 5.7
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_SqlPartWidget(object):
    def setupUi(self, SqlPartWidget):
        SqlPartWidget.setObjectName("SqlPartWidget")
        SqlPartWidget.resize(602, 223)
        self.verticalLayout = QtWidgets.QVBoxLayout(SqlPartWidget)
        self.verticalLayout.setContentsMargins(4, 4, 4, 4)
        self.verticalLayout.setSpacing(2)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label_parameters = QtWidgets.QLabel(SqlPartWidget)
        self.label_parameters.setObjectName("label_parameters")
        self.horizontalLayout.addWidget(self.label_parameters)
        self.parameters = CallParameters(SqlPartWidget)
        self.parameters.setReadOnly(True)
        self.parameters.setObjectName("parameters")
        self.horizontalLayout.addWidget(self.parameters)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.script = ScriptEditBox(SqlPartWidget)
        self.script.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.script.setReadOnly(True)
        self.script.setObjectName("script")
        self.verticalLayout.addWidget(self.script)

        self.retranslateUi(SqlPartWidget)
        QtCore.QMetaObject.connectSlotsByName(SqlPartWidget)

    def retranslateUi(self, SqlPartWidget):
        _translate = QtCore.QCoreApplication.translate
        self.label_parameters.setText(_translate("SqlPartWidget", "Parameters:"))

from .custom_widgets import CallParameters, ScriptEditBox
