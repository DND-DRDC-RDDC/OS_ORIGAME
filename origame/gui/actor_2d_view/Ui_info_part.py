# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_files\info_part.ui'
#
# Created by: PyQt5 UI code generator 5.7
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_InfoPartWidget(object):
    def setupUi(self, InfoPartWidget):
        InfoPartWidget.setObjectName("InfoPartWidget")
        InfoPartWidget.resize(457, 357)
        self.horizontalLayout = QtWidgets.QHBoxLayout(InfoPartWidget)
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.textBrowser = InfoTextBrowser(InfoPartWidget)
        self.textBrowser.setAutoFillBackground(True)
        self.textBrowser.setFrameShadow(QtWidgets.QFrame.Plain)
        self.textBrowser.setLineWidth(0)
        self.textBrowser.setObjectName("textBrowser")
        self.horizontalLayout.addWidget(self.textBrowser)

        self.retranslateUi(InfoPartWidget)
        QtCore.QMetaObject.connectSlotsByName(InfoPartWidget)

    def retranslateUi(self, InfoPartWidget):
        pass

from .custom_widgets import InfoTextBrowser
