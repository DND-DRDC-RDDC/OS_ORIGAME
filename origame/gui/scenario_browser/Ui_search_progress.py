# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_files\search_progress.ui'
#
# Created by: PyQt5 UI code generator 5.7
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_SearchProgressDialog(object):
    def setupUi(self, SearchProgressDialog):
        SearchProgressDialog.setObjectName("SearchProgressDialog")
        SearchProgressDialog.resize(562, 78)
        SearchProgressDialog.setSizeGripEnabled(True)
        SearchProgressDialog.setModal(True)
        self.verticalLayout = QtWidgets.QVBoxLayout(SearchProgressDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.widget = QtWidgets.QWidget(SearchProgressDialog)
        self.widget.setObjectName("widget")
        self.horizontalLayout = QtWidgets.QHBoxLayout(self.widget)
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.current_part_label_name = QtWidgets.QLabel(self.widget)
        self.current_part_label_name.setObjectName("current_part_label_name")
        self.horizontalLayout.addWidget(self.current_part_label_name)
        self.part_path_label = QtWidgets.QLabel(self.widget)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.part_path_label.sizePolicy().hasHeightForWidth())
        self.part_path_label.setSizePolicy(sizePolicy)
        self.part_path_label.setObjectName("part_path_label")
        self.horizontalLayout.addWidget(self.part_path_label)
        self.verticalLayout.addWidget(self.widget)
        self.buttonBox = QtWidgets.QDialogButtonBox(SearchProgressDialog)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(SearchProgressDialog)
        self.buttonBox.accepted.connect(SearchProgressDialog.accept)
        self.buttonBox.rejected.connect(SearchProgressDialog.reject)
        QtCore.QMetaObject.connectSlotsByName(SearchProgressDialog)

    def retranslateUi(self, SearchProgressDialog):
        _translate = QtCore.QCoreApplication.translate
        SearchProgressDialog.setWindowTitle(_translate("SearchProgressDialog", "Search Progress"))
        self.current_part_label_name.setText(_translate("SearchProgressDialog", "Current Part: "))
        self.part_path_label.setText(_translate("SearchProgressDialog", "the path of the part"))

