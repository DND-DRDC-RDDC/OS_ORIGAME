# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\origame\gui\actor_2d_view\ui_files\variable_part.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_VariablePartWidget(object):
    def setupUi(self, VariablePartWidget):
        VariablePartWidget.setObjectName("VariablePartWidget")
        VariablePartWidget.resize(343, 38)
        self.horizontalLayout = QtWidgets.QHBoxLayout(VariablePartWidget)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtWidgets.QLabel(VariablePartWidget)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.variable_data = QtWidgets.QLabel(VariablePartWidget)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.variable_data.sizePolicy().hasHeightForWidth())
        self.variable_data.setSizePolicy(sizePolicy)
        self.variable_data.setText("")
        self.variable_data.setObjectName("variable_data")
        self.horizontalLayout.addWidget(self.variable_data)

        self.retranslateUi(VariablePartWidget)
        QtCore.QMetaObject.connectSlotsByName(VariablePartWidget)

    def retranslateUi(self, VariablePartWidget):
        _translate = QtCore.QCoreApplication.translate
        self.label.setText(_translate("VariablePartWidget", "Value = "))

