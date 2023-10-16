# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\origame\gui\ui_files\input_parameters.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_InputParametersDialog(object):
    def setupUi(self, InputParametersDialog):
        InputParametersDialog.setObjectName("InputParametersDialog")
        InputParametersDialog.resize(698, 257)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(InputParametersDialog.sizePolicy().hasHeightForWidth())
        InputParametersDialog.setSizePolicy(sizePolicy)
        self.verticalLayout = QtWidgets.QVBoxLayout(InputParametersDialog)
        self.verticalLayout.setContentsMargins(9, 3, 9, 0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.label = QtWidgets.QLabel(InputParametersDialog)
        self.label.setObjectName("label")
        self.verticalLayout.addWidget(self.label)
        self.label_2 = QtWidgets.QLabel(InputParametersDialog)
        self.label_2.setObjectName("label_2")
        self.verticalLayout.addWidget(self.label_2)
        self.parameter_area = QtWidgets.QScrollArea(InputParametersDialog)
        self.parameter_area.setWidgetResizable(True)
        self.parameter_area.setObjectName("parameter_area")
        self.scrollAreaWidgetContents = QtWidgets.QWidget()
        self.scrollAreaWidgetContents.setGeometry(QtCore.QRect(0, 0, 678, 185))
        self.scrollAreaWidgetContents.setObjectName("scrollAreaWidgetContents")
        self.formLayout = QtWidgets.QFormLayout(self.scrollAreaWidgetContents)
        self.formLayout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.formLayout.setContentsMargins(10, 10, 10, 11)
        self.formLayout.setObjectName("formLayout")
        self.parameter_area.setWidget(self.scrollAreaWidgetContents)
        self.verticalLayout.addWidget(self.parameter_area)
        self.buttonBox = QtWidgets.QDialogButtonBox(InputParametersDialog)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(InputParametersDialog)
        self.buttonBox.accepted.connect(InputParametersDialog.accept) # type: ignore
        self.buttonBox.rejected.connect(InputParametersDialog.reject) # type: ignore
        QtCore.QMetaObject.connectSlotsByName(InputParametersDialog)

    def retranslateUi(self, InputParametersDialog):
        _translate = QtCore.QCoreApplication.translate
        InputParametersDialog.setWindowTitle(_translate("InputParametersDialog", "Input Parameters"))
        self.label.setText(_translate("InputParametersDialog", "Enter a valid Python expression in each field. Each expression will be evaluated by Python before the function is called."))
        self.label_2.setText(_translate("InputParametersDialog", "Click OK to Run the function with the following parameters.... Click Cancel to abandon running the function."))
