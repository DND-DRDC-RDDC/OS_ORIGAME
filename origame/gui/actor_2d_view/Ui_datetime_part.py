# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_files\datetime_part.ui'
#
# Created by: PyQt5 UI code generator 5.7
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_DateTimePartWidget(object):
    def setupUi(self, DateTimePartWidget):
        DateTimePartWidget.setObjectName("DateTimePartWidget")
        DateTimePartWidget.resize(165, 64)
        DateTimePartWidget.setStyleSheet("font: 8pt \"MS Shell Dlg 2\";background-color: rgb(255, 255, 255);")
        self.formLayout = QtWidgets.QFormLayout(DateTimePartWidget)
        self.formLayout.setObjectName("formLayout")
        self.label = QtWidgets.QLabel(DateTimePartWidget)
        self.label.setObjectName("label")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label)
        self.date_edit = QtWidgets.QLineEdit(DateTimePartWidget)
        self.date_edit.setEnabled(False)
        self.date_edit.setReadOnly(True)
        self.date_edit.setObjectName("date_edit")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.date_edit)
        self.label_2 = QtWidgets.QLabel(DateTimePartWidget)
        self.label_2.setObjectName("label_2")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.label_2)
        self.time_edit = QtWidgets.QLineEdit(DateTimePartWidget)
        self.time_edit.setEnabled(False)
        self.time_edit.setObjectName("time_edit")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.time_edit)

        self.retranslateUi(DateTimePartWidget)
        QtCore.QMetaObject.connectSlotsByName(DateTimePartWidget)

    def retranslateUi(self, DateTimePartWidget):
        _translate = QtCore.QCoreApplication.translate
        self.label.setText(_translate("DateTimePartWidget", "Date:"))
        self.label_2.setText(_translate("DateTimePartWidget", "Time:"))

