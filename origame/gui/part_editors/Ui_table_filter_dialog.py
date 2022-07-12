# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'table_filter_dialog.ui'
#
# Created by: PyQt5 UI code generator 5.7
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_TableFilterDialog(object):
    def setupUi(self, TableFilterDialog):
        TableFilterDialog.setObjectName("TableFilterDialog")
        TableFilterDialog.resize(400, 102)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(TableFilterDialog.sizePolicy().hasHeightForWidth())
        TableFilterDialog.setSizePolicy(sizePolicy)
        TableFilterDialog.setMinimumSize(QtCore.QSize(0, 102))
        TableFilterDialog.setMaximumSize(QtCore.QSize(16777215, 102))
        self.verticalLayout = QtWidgets.QVBoxLayout(TableFilterDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.label = QtWidgets.QLabel(TableFilterDialog)
        self.label.setWordWrap(True)
        self.label.setObjectName("label")
        self.verticalLayout.addWidget(self.label)
        self.formLayout = QtWidgets.QFormLayout()
        self.formLayout.setObjectName("formLayout")
        self.sql_filter_line_edit = QtWidgets.QLineEdit(TableFilterDialog)
        self.sql_filter_line_edit.setText("")
        self.sql_filter_line_edit.setObjectName("sql_filter_line_edit")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.sql_filter_line_edit)
        self.verticalLayout.addLayout(self.formLayout)
        self.button_box = QtWidgets.QDialogButtonBox(TableFilterDialog)
        self.button_box.setOrientation(QtCore.Qt.Horizontal)
        self.button_box.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.button_box.setObjectName("button_box")
        self.verticalLayout.addWidget(self.button_box)

        self.retranslateUi(TableFilterDialog)
        self.button_box.accepted.connect(TableFilterDialog.accept)
        self.button_box.rejected.connect(TableFilterDialog.reject)
        QtCore.QMetaObject.connectSlotsByName(TableFilterDialog)

    def retranslateUi(self, TableFilterDialog):
        _translate = QtCore.QCoreApplication.translate
        TableFilterDialog.setWindowTitle(_translate("TableFilterDialog", "Filter"))
        self.label.setText(_translate("TableFilterDialog", "Click OK to apply the SQLite WHERE statement and filter the table data (data will not be filtered in the editor)."))
        self.sql_filter_line_edit.setPlaceholderText(_translate("TableFilterDialog", "SQL \'WHERE\' Example: [Col1] = \'value\'"))

