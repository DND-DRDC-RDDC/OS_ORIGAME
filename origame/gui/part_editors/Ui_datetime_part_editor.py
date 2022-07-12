# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_files\datetime_part_editor.ui'
#
# Created by: PyQt5 UI code generator 5.7
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_DateTimePartEditorWidget(object):
    def setupUi(self, DateTimePartEditorWidget):
        DateTimePartEditorWidget.setObjectName("DateTimePartEditorWidget")
        DateTimePartEditorWidget.resize(132, 64)
        self.formLayout = QtWidgets.QFormLayout(DateTimePartEditorWidget)
        self.formLayout.setObjectName("formLayout")
        self.label = QtWidgets.QLabel(DateTimePartEditorWidget)
        self.label.setObjectName("label")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label)
        self.date_edit = QtWidgets.QDateEdit(DateTimePartEditorWidget)
        self.date_edit.setObjectName("date_edit")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.date_edit)
        self.label_2 = QtWidgets.QLabel(DateTimePartEditorWidget)
        self.label_2.setObjectName("label_2")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.label_2)
        self.time_edit = QtWidgets.QTimeEdit(DateTimePartEditorWidget)
        self.time_edit.setObjectName("time_edit")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.time_edit)

        self.retranslateUi(DateTimePartEditorWidget)
        QtCore.QMetaObject.connectSlotsByName(DateTimePartEditorWidget)

    def retranslateUi(self, DateTimePartEditorWidget):
        _translate = QtCore.QCoreApplication.translate
        self.label.setText(_translate("DateTimePartEditorWidget", "Date:"))
        self.date_edit.setDisplayFormat(_translate("DateTimePartEditorWidget", "yyyy/MM/dd"))
        self.label_2.setText(_translate("DateTimePartEditorWidget", "Time:"))
        self.time_edit.setDisplayFormat(_translate("DateTimePartEditorWidget", "hh:mm:ss"))

