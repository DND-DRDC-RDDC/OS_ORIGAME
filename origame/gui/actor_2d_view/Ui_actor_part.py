# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_files\actor_part.ui'
#
# Created by: PyQt5 UI code generator 5.7
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_ActorPartWidget(object):
    def setupUi(self, ActorPartWidget):
        ActorPartWidget.setObjectName("ActorPartWidget")
        ActorPartWidget.resize(400, 300)
        self.horizontalLayout = QtWidgets.QHBoxLayout(ActorPartWidget)
        self.horizontalLayout.setObjectName("horizontalLayout")

        self.retranslateUi(ActorPartWidget)
        QtCore.QMetaObject.connectSlotsByName(ActorPartWidget)

    def retranslateUi(self, ActorPartWidget):
        _translate = QtCore.QCoreApplication.translate
        ActorPartWidget.setWindowTitle(_translate("ActorPartWidget", "Form"))

