# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\origame\gui\sim\main\ui_files\edit_time_dialog.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_EditTimeDialog(object):
    def setupUi(self, EditTimeDialog):
        EditTimeDialog.setObjectName("EditTimeDialog")
        EditTimeDialog.resize(300, 175)
        EditTimeDialog.setMinimumSize(QtCore.QSize(300, 175))
        EditTimeDialog.setMaximumSize(QtCore.QSize(300, 175))
        self.verticalLayout = QtWidgets.QVBoxLayout(EditTimeDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtWidgets.QLabel(EditTimeDialog)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.days_spinbox = QtWidgets.QSpinBox(EditTimeDialog)
        self.days_spinbox.setMaximum(999999999)
        self.days_spinbox.setObjectName("days_spinbox")
        self.horizontalLayout.addWidget(self.days_spinbox)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.label_2 = QtWidgets.QLabel(EditTimeDialog)
        self.label_2.setObjectName("label_2")
        self.horizontalLayout_2.addWidget(self.label_2)
        self.hours_spinbox = QtWidgets.QSpinBox(EditTimeDialog)
        self.hours_spinbox.setMaximum(24)
        self.hours_spinbox.setObjectName("hours_spinbox")
        self.horizontalLayout_2.addWidget(self.hours_spinbox)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.label_3 = QtWidgets.QLabel(EditTimeDialog)
        self.label_3.setObjectName("label_3")
        self.horizontalLayout_3.addWidget(self.label_3)
        self.minutes_spinbox = QtWidgets.QSpinBox(EditTimeDialog)
        self.minutes_spinbox.setMaximum(60)
        self.minutes_spinbox.setObjectName("minutes_spinbox")
        self.horizontalLayout_3.addWidget(self.minutes_spinbox)
        self.verticalLayout.addLayout(self.horizontalLayout_3)
        self.horizontalLayout_4 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        self.label_4 = QtWidgets.QLabel(EditTimeDialog)
        self.label_4.setObjectName("label_4")
        self.horizontalLayout_4.addWidget(self.label_4)
        self.seconds_spinbox = QtWidgets.QSpinBox(EditTimeDialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.seconds_spinbox.sizePolicy().hasHeightForWidth())
        self.seconds_spinbox.setSizePolicy(sizePolicy)
        self.seconds_spinbox.setMinimumSize(QtCore.QSize(0, 0))
        self.seconds_spinbox.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.seconds_spinbox.setMaximum(60)
        self.seconds_spinbox.setObjectName("seconds_spinbox")
        self.horizontalLayout_4.addWidget(self.seconds_spinbox)
        self.verticalLayout.addLayout(self.horizontalLayout_4)
        self.buttonBox = QtWidgets.QDialogButtonBox(EditTimeDialog)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(EditTimeDialog)
        self.buttonBox.accepted.connect(EditTimeDialog.accept) # type: ignore
        self.buttonBox.rejected.connect(EditTimeDialog.reject) # type: ignore
        QtCore.QMetaObject.connectSlotsByName(EditTimeDialog)

    def retranslateUi(self, EditTimeDialog):
        _translate = QtCore.QCoreApplication.translate
        EditTimeDialog.setWindowTitle(_translate("EditTimeDialog", "Edit Time"))
        self.label.setText(_translate("EditTimeDialog", "Days:"))
        self.label_2.setText(_translate("EditTimeDialog", "Hours:"))
        self.label_3.setText(_translate("EditTimeDialog", "Minutes:"))
        self.label_4.setText(_translate("EditTimeDialog", "Seconds:"))

