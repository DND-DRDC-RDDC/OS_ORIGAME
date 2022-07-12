# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_files\label_button_item.ui'
#
# Created by: PyQt5 UI code generator 5.7
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_LabelButtonItem(object):
    def setupUi(self, LabelButtonItem):
        LabelButtonItem.setObjectName("LabelButtonItem")
        LabelButtonItem.resize(398, 41)
        self.horizontalLayout = QtWidgets.QHBoxLayout(LabelButtonItem)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtWidgets.QLabel(LabelButtonItem)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.pushButton = QtWidgets.QPushButton(LabelButtonItem)
        self.pushButton.setObjectName("pushButton")
        self.horizontalLayout.addWidget(self.pushButton)

        self.retranslateUi(LabelButtonItem)
        QtCore.QMetaObject.connectSlotsByName(LabelButtonItem)

    def retranslateUi(self, LabelButtonItem):
        _translate = QtCore.QCoreApplication.translate
        self.label.setText(_translate("LabelButtonItem", "TextLabel"))
        self.pushButton.setText(_translate("LabelButtonItem", "Run"))

