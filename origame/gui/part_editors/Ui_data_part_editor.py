# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\origame\gui\part_editors\ui_files\data_part_editor.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_DataPartEditorWidget(object):
    def setupUi(self, DataPartEditorWidget):
        DataPartEditorWidget.setObjectName("DataPartEditorWidget")
        DataPartEditorWidget.resize(654, 404)
        self.verticalLayout = QtWidgets.QVBoxLayout(DataPartEditorWidget)
        self.verticalLayout.setObjectName("verticalLayout")
        self.widget = QtWidgets.QWidget(DataPartEditorWidget)
        self.widget.setObjectName("widget")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.widget)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.horizontalLayout_5 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_5.setObjectName("horizontalLayout_5")
        self.insert_before_button = QtWidgets.QPushButton(self.widget)
        self.insert_before_button.setMaximumSize(QtCore.QSize(40, 16777215))
        self.insert_before_button.setObjectName("insert_before_button")
        self.horizontalLayout_5.addWidget(self.insert_before_button)
        self.insert_after_button = QtWidgets.QPushButton(self.widget)
        self.insert_after_button.setMaximumSize(QtCore.QSize(40, 16777215))
        self.insert_after_button.setObjectName("insert_after_button")
        self.horizontalLayout_5.addWidget(self.insert_after_button)
        self.select_all_button = QtWidgets.QPushButton(self.widget)
        self.select_all_button.setMaximumSize(QtCore.QSize(40, 16777215))
        self.select_all_button.setObjectName("select_all_button")
        self.horizontalLayout_5.addWidget(self.select_all_button)
        self.cut_button = QtWidgets.QPushButton(self.widget)
        self.cut_button.setMaximumSize(QtCore.QSize(40, 16777215))
        self.cut_button.setObjectName("cut_button")
        self.horizontalLayout_5.addWidget(self.cut_button)
        self.copy_button = QtWidgets.QPushButton(self.widget)
        self.copy_button.setMaximumSize(QtCore.QSize(40, 16777215))
        self.copy_button.setObjectName("copy_button")
        self.horizontalLayout_5.addWidget(self.copy_button)
        self.paste_button = QtWidgets.QPushButton(self.widget)
        self.paste_button.setMaximumSize(QtCore.QSize(40, 16777215))
        self.paste_button.setObjectName("paste_button")
        self.horizontalLayout_5.addWidget(self.paste_button)
        self.del_button = QtWidgets.QPushButton(self.widget)
        self.del_button.setMaximumSize(QtCore.QSize(40, 16777215))
        self.del_button.setObjectName("del_button")
        self.horizontalLayout_5.addWidget(self.del_button)
        self.move_up_button = QtWidgets.QPushButton(self.widget)
        self.move_up_button.setMaximumSize(QtCore.QSize(40, 16777215))
        self.move_up_button.setObjectName("move_up_button")
        self.horizontalLayout_5.addWidget(self.move_up_button)
        self.move_down_button = QtWidgets.QPushButton(self.widget)
        self.move_down_button.setMaximumSize(QtCore.QSize(40, 16777215))
        self.move_down_button.setObjectName("move_down_button")
        self.horizontalLayout_5.addWidget(self.move_down_button)
        spacerItem = QtWidgets.QSpacerItem(108, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout_5.addItem(spacerItem)
        self.verticalLayout_2.addLayout(self.horizontalLayout_5)
        self.main_part_editor_layout = QtWidgets.QHBoxLayout()
        self.main_part_editor_layout.setObjectName("main_part_editor_layout")
        self.tableView = QtWidgets.QTableView(self.widget)
        self.tableView.setObjectName("tableView")
        self.main_part_editor_layout.addWidget(self.tableView)
        self.verticalLayout_2.addLayout(self.main_part_editor_layout)
        self.verticalLayout.addWidget(self.widget)

        self.retranslateUi(DataPartEditorWidget)
        QtCore.QMetaObject.connectSlotsByName(DataPartEditorWidget)

    def retranslateUi(self, DataPartEditorWidget):
        _translate = QtCore.QCoreApplication.translate
        DataPartEditorWidget.setWindowTitle(_translate("DataPartEditorWidget", "Form"))
        self.insert_before_button.setText(_translate("DataPartEditorWidget", "Insert before"))
        self.insert_after_button.setText(_translate("DataPartEditorWidget", "Insert after"))
        self.select_all_button.setText(_translate("DataPartEditorWidget", "Select all"))
        self.cut_button.setText(_translate("DataPartEditorWidget", "Cut"))
        self.copy_button.setText(_translate("DataPartEditorWidget", "Copy"))
        self.paste_button.setText(_translate("DataPartEditorWidget", "Paste"))
        self.del_button.setText(_translate("DataPartEditorWidget", "Del"))
        self.move_up_button.setText(_translate("DataPartEditorWidget", "Move up"))
        self.move_down_button.setText(_translate("DataPartEditorWidget", "Move down"))

