# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\origame\gui\ui_files\context_help.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_ContextHelp(object):
    def setupUi(self, ContextHelp):
        ContextHelp.setObjectName("ContextHelp")
        ContextHelp.resize(400, 300)
        self.gridLayout_2 = QtWidgets.QGridLayout(ContextHelp)
        self.gridLayout_2.setContentsMargins(6, 6, 6, 6)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.gridLayout = QtWidgets.QGridLayout()
        self.gridLayout.setSpacing(6)
        self.gridLayout.setObjectName("gridLayout")
        self.label_part_type = QtWidgets.QLabel(ContextHelp)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_part_type.sizePolicy().hasHeightForWidth())
        self.label_part_type.setSizePolicy(sizePolicy)
        self.label_part_type.setObjectName("label_part_type")
        self.gridLayout.addWidget(self.label_part_type, 0, 1, 1, 1)
        self.label_2 = QtWidgets.QLabel(ContextHelp)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_2.sizePolicy().hasHeightForWidth())
        self.label_2.setSizePolicy(sizePolicy)
        self.label_2.setTextFormat(QtCore.Qt.RichText)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.label_part_name = QtWidgets.QLabel(ContextHelp)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_part_name.sizePolicy().hasHeightForWidth())
        self.label_part_name.setSizePolicy(sizePolicy)
        self.label_part_name.setObjectName("label_part_name")
        self.gridLayout.addWidget(self.label_part_name, 1, 1, 1, 1)
        self.label_1 = QtWidgets.QLabel(ContextHelp)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_1.sizePolicy().hasHeightForWidth())
        self.label_1.setSizePolicy(sizePolicy)
        self.label_1.setTextFormat(QtCore.Qt.RichText)
        self.label_1.setObjectName("label_1")
        self.gridLayout.addWidget(self.label_1, 0, 0, 1, 1)
        self.text_help = QtWidgets.QTextEdit(ContextHelp)
        self.text_help.setEnabled(True)
        self.text_help.setUndoRedoEnabled(False)
        self.text_help.setReadOnly(True)
        self.text_help.setObjectName("text_help")
        self.gridLayout.addWidget(self.text_help, 2, 0, 1, 2)
        self.gridLayout_2.addLayout(self.gridLayout, 0, 0, 1, 1)

        self.retranslateUi(ContextHelp)
        QtCore.QMetaObject.connectSlotsByName(ContextHelp)

    def retranslateUi(self, ContextHelp):
        _translate = QtCore.QCoreApplication.translate
        ContextHelp.setWindowTitle(_translate("ContextHelp", "Form"))
        self.label_part_type.setText(_translate("ContextHelp", "<type of part>"))
        self.label_2.setText(_translate("ContextHelp", "<b>Part Name:</b>"))
        self.label_part_name.setText(_translate("ContextHelp", "<name of part>"))
        self.label_1.setText(_translate("ContextHelp", "<b>Part Type:</b>"))

