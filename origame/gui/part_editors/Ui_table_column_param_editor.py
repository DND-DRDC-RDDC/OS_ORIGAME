# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\origame\gui\part_editors\ui_files\table_column_param_editor.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_edit_column_parameters(object):
    def setupUi(self, edit_column_parameters):
        edit_column_parameters.setObjectName("edit_column_parameters")
        edit_column_parameters.resize(317, 100)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(edit_column_parameters.sizePolicy().hasHeightForWidth())
        edit_column_parameters.setSizePolicy(sizePolicy)
        edit_column_parameters.setMinimumSize(QtCore.QSize(0, 100))
        edit_column_parameters.setMaximumSize(QtCore.QSize(16777215, 100))
        self.verticalLayout = QtWidgets.QVBoxLayout(edit_column_parameters)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtWidgets.QLabel(edit_column_parameters)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy)
        self.label.setMinimumSize(QtCore.QSize(35, 0))
        self.label.setMaximumSize(QtCore.QSize(35, 16777215))
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.col_name_linedit = QtWidgets.QLineEdit(edit_column_parameters)
        self.col_name_linedit.setObjectName("col_name_linedit")
        self.horizontalLayout.addWidget(self.col_name_linedit)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.label_2 = QtWidgets.QLabel(edit_column_parameters)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_2.sizePolicy().hasHeightForWidth())
        self.label_2.setSizePolicy(sizePolicy)
        self.label_2.setMinimumSize(QtCore.QSize(35, 0))
        self.label_2.setMaximumSize(QtCore.QSize(35, 16777215))
        self.label_2.setObjectName("label_2")
        self.horizontalLayout_2.addWidget(self.label_2)
        self.col_type_combobox = QtWidgets.QComboBox(edit_column_parameters)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.col_type_combobox.sizePolicy().hasHeightForWidth())
        self.col_type_combobox.setSizePolicy(sizePolicy)
        self.col_type_combobox.setObjectName("col_type_combobox")
        self.col_type_combobox.addItem("")
        self.col_type_combobox.addItem("")
        self.col_type_combobox.addItem("")
        self.col_type_combobox.addItem("")
        self.horizontalLayout_2.addWidget(self.col_type_combobox)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.buttonBox = QtWidgets.QDialogButtonBox(edit_column_parameters)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(edit_column_parameters)
        self.buttonBox.accepted.connect(edit_column_parameters.accept) # type: ignore
        self.buttonBox.rejected.connect(edit_column_parameters.reject) # type: ignore
        QtCore.QMetaObject.connectSlotsByName(edit_column_parameters)

    def retranslateUi(self, edit_column_parameters):
        _translate = QtCore.QCoreApplication.translate
        edit_column_parameters.setWindowTitle(_translate("edit_column_parameters", "Edit Column Parameters"))
        self.label.setText(_translate("edit_column_parameters", "Name: "))
        self.label_2.setText(_translate("edit_column_parameters", "Type: "))
        self.col_type_combobox.setItemText(0, _translate("edit_column_parameters", "DATETIME"))
        self.col_type_combobox.setItemText(1, _translate("edit_column_parameters", "INTEGER"))
        self.col_type_combobox.setItemText(2, _translate("edit_column_parameters", "REAL"))
        self.col_type_combobox.setItemText(3, _translate("edit_column_parameters", "TEXT"))

