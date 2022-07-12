# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_files\special_value_editor.ui'
#
# Created by: PyQt5 UI code generator 5.7
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_SpecialValueEditor(object):
    def setupUi(self, SpecialValueEditor):
        SpecialValueEditor.setObjectName("SpecialValueEditor")
        SpecialValueEditor.resize(486, 388)
        self.verticalLayout = QtWidgets.QVBoxLayout(SpecialValueEditor)
        self.verticalLayout.setObjectName("verticalLayout")
        self.label = QtWidgets.QLabel(SpecialValueEditor)
        self.label.setObjectName("label")
        self.verticalLayout.addWidget(self.label)
        self.value_edit = QtWidgets.QTextEdit(SpecialValueEditor)
        self.value_edit.setObjectName("value_edit")
        self.verticalLayout.addWidget(self.value_edit)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        spacerItem = QtWidgets.QSpacerItem(48, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.button_box = QtWidgets.QDialogButtonBox(SpecialValueEditor)
        self.button_box.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.button_box.setObjectName("button_box")
        self.horizontalLayout.addWidget(self.button_box)
        self.verticalLayout.addLayout(self.horizontalLayout)

        self.retranslateUi(SpecialValueEditor)
        QtCore.QMetaObject.connectSlotsByName(SpecialValueEditor)

    def retranslateUi(self, SpecialValueEditor):
        _translate = QtCore.QCoreApplication.translate
        SpecialValueEditor.setWindowTitle(_translate("SpecialValueEditor", "Special Value Editor"))
        self.label.setText(_translate("SpecialValueEditor", "Enter a valid Python expression:"))

