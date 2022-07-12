# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_files\progress_indicator.ui'
#
# Created by: PyQt5 UI code generator 5.7
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_ProgressIndicator(object):
    def setupUi(self, ProgressIndicator):
        ProgressIndicator.setObjectName("ProgressIndicator")
        ProgressIndicator.resize(158, 31)
        self.horizontalLayout = QtWidgets.QHBoxLayout(ProgressIndicator)
        self.horizontalLayout.setContentsMargins(2, 2, 2, 2)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label_operation = QtWidgets.QLabel(ProgressIndicator)
        self.label_operation.setObjectName("label_operation")
        self.horizontalLayout.addWidget(self.label_operation)
        self.progress_bar = QtWidgets.QProgressBar(ProgressIndicator)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.progress_bar.sizePolicy().hasHeightForWidth())
        self.progress_bar.setSizePolicy(sizePolicy)
        self.progress_bar.setMaximumSize(QtCore.QSize(150, 10))
        self.progress_bar.setMaximum(0)
        self.progress_bar.setProperty("value", 0)
        self.progress_bar.setAlignment(QtCore.Qt.AlignLeading|QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setInvertedAppearance(False)
        self.progress_bar.setObjectName("progress_bar")
        self.horizontalLayout.addWidget(self.progress_bar)

        self.retranslateUi(ProgressIndicator)
        QtCore.QMetaObject.connectSlotsByName(ProgressIndicator)

    def retranslateUi(self, ProgressIndicator):
        _translate = QtCore.QCoreApplication.translate
        ProgressIndicator.setWindowTitle(_translate("ProgressIndicator", "ProgressIndicator"))
        self.label_operation.setText(_translate("ProgressIndicator", "Operation"))
        self.progress_bar.setFormat(_translate("ProgressIndicator", "%p%"))

