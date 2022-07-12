# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_files\info_part_editor.ui'
#
# Created by: PyQt5 UI code generator 5.7
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_InfoPartEditorWidget(object):
    def setupUi(self, InfoPartEditorWidget):
        InfoPartEditorWidget.setObjectName("InfoPartEditorWidget")
        InfoPartEditorWidget.resize(559, 400)
        self.verticalLayout = QtWidgets.QVBoxLayout(InfoPartEditorWidget)
        self.verticalLayout.setObjectName("verticalLayout")
        self.info_text = QtWidgets.QTextEdit(InfoPartEditorWidget)
        self.info_text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.info_text.setObjectName("info_text")
        self.verticalLayout.addWidget(self.info_text)

        self.retranslateUi(InfoPartEditorWidget)
        QtCore.QMetaObject.connectSlotsByName(InfoPartEditorWidget)

    def retranslateUi(self, InfoPartEditorWidget):
        _translate = QtCore.QCoreApplication.translate
        InfoPartEditorWidget.setWindowTitle(_translate("InfoPartEditorWidget", "Form"))

