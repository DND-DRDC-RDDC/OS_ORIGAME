# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\origame\gui\actor_2d_view\ui_files\file_part.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_FilePartWidget(object):
    def setupUi(self, FilePartWidget):
        FilePartWidget.setObjectName("FilePartWidget")
        FilePartWidget.resize(580, 111)
        self.label = QtWidgets.QLabel(FilePartWidget)
        self.label.setGeometry(QtCore.QRect(10, 20, 45, 16))
        self.label.setObjectName("label")
        self.relative_to_scen_folder = QtWidgets.QCheckBox(FilePartWidget)
        self.relative_to_scen_folder.setEnabled(False)
        self.relative_to_scen_folder.setGeometry(QtCore.QRect(10, 70, 152, 17))
        self.relative_to_scen_folder.setCheckable(True)
        self.relative_to_scen_folder.setObjectName("relative_to_scen_folder")
        self.filepath = QtWidgets.QTextEdit(FilePartWidget)
        self.filepath.setGeometry(QtCore.QRect(63, 20, 481, 41))
        self.filepath.setReadOnly(True)
        self.filepath.setObjectName("filepath")

        self.retranslateUi(FilePartWidget)
        QtCore.QMetaObject.connectSlotsByName(FilePartWidget)

    def retranslateUi(self, FilePartWidget):
        _translate = QtCore.QCoreApplication.translate
        self.label.setText(_translate("FilePartWidget", "File Path:"))
        self.relative_to_scen_folder.setText(_translate("FilePartWidget", "Relative to Scenario Folder"))

