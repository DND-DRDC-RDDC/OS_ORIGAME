# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_files\time_part.ui'
#
# Created by: PyQt5 UI code generator 5.7
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_TimePartWidget(object):
    def setupUi(self, TimePartWidget):
        TimePartWidget.setObjectName("TimePartWidget")
        TimePartWidget.resize(198, 38)
        TimePartWidget.setStyleSheet("font: 8pt \"MS Shell Dlg 2\";background-color: rgb(255, 255, 255);")
        self.formLayout = QtWidgets.QFormLayout(TimePartWidget)
        self.formLayout.setObjectName("formLayout")
        self.label = QtWidgets.QLabel(TimePartWidget)
        self.label.setObjectName("label")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label)
        self.elapsed_time = QtWidgets.QLineEdit(TimePartWidget)
        self.elapsed_time.setEnabled(False)
        self.elapsed_time.setReadOnly(True)
        self.elapsed_time.setObjectName("elapsed_time")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.elapsed_time)

        self.retranslateUi(TimePartWidget)
        QtCore.QMetaObject.connectSlotsByName(TimePartWidget)

    def retranslateUi(self, TimePartWidget):
        _translate = QtCore.QCoreApplication.translate
        self.label.setText(_translate("TimePartWidget", "Elapsed Time:"))

