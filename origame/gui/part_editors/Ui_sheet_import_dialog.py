# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\origame\gui\part_editors\ui_files\sheet_import_dialog.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_SheetImportDialog(object):
    def setupUi(self, SheetImportDialog):
        SheetImportDialog.setObjectName("SheetImportDialog")
        SheetImportDialog.resize(500, 200)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(SheetImportDialog.sizePolicy().hasHeightForWidth())
        SheetImportDialog.setSizePolicy(sizePolicy)
        SheetImportDialog.setMinimumSize(QtCore.QSize(0, 200))
        SheetImportDialog.setMaximumSize(QtCore.QSize(16777215, 200))
        self.verticalLayout = QtWidgets.QVBoxLayout(SheetImportDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.instructions_label = QtWidgets.QLabel(SheetImportDialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.instructions_label.sizePolicy().hasHeightForWidth())
        self.instructions_label.setSizePolicy(sizePolicy)
        self.instructions_label.setWordWrap(True)
        self.instructions_label.setObjectName("instructions_label")
        self.verticalLayout.addWidget(self.instructions_label)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.file_label = QtWidgets.QLabel(SheetImportDialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.file_label.sizePolicy().hasHeightForWidth())
        self.file_label.setSizePolicy(sizePolicy)
        self.file_label.setMinimumSize(QtCore.QSize(45, 0))
        self.file_label.setMaximumSize(QtCore.QSize(45, 16777215))
        self.file_label.setObjectName("file_label")
        self.horizontalLayout.addWidget(self.file_label)
        self.filepath_linedit = QtWidgets.QLineEdit(SheetImportDialog)
        self.filepath_linedit.setText("")
        self.filepath_linedit.setObjectName("filepath_linedit")
        self.horizontalLayout.addWidget(self.filepath_linedit)
        self.browse_files_button = QtWidgets.QPushButton(SheetImportDialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.browse_files_button.sizePolicy().hasHeightForWidth())
        self.browse_files_button.setSizePolicy(sizePolicy)
        self.browse_files_button.setMinimumSize(QtCore.QSize(30, 0))
        self.browse_files_button.setMaximumSize(QtCore.QSize(30, 16777215))
        self.browse_files_button.setObjectName("browse_files_button")
        self.horizontalLayout.addWidget(self.browse_files_button)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.horizontalLayout_4 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        spacerItem = QtWidgets.QSpacerItem(50, 20, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout_4.addItem(spacerItem)
        self.list_sheets_button = QtWidgets.QPushButton(SheetImportDialog)
        self.list_sheets_button.setObjectName("list_sheets_button")
        self.horizontalLayout_4.addWidget(self.list_sheets_button)
        self.verticalLayout.addLayout(self.horizontalLayout_4)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.sheet_label = QtWidgets.QLabel(SheetImportDialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.sheet_label.sizePolicy().hasHeightForWidth())
        self.sheet_label.setSizePolicy(sizePolicy)
        self.sheet_label.setMinimumSize(QtCore.QSize(45, 0))
        self.sheet_label.setMaximumSize(QtCore.QSize(45, 16777215))
        self.sheet_label.setObjectName("sheet_label")
        self.horizontalLayout_2.addWidget(self.sheet_label)
        self.sheet_combobox = QtWidgets.QComboBox(SheetImportDialog)
        self.sheet_combobox.setObjectName("sheet_combobox")
        self.horizontalLayout_2.addWidget(self.sheet_combobox)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.range_label = QtWidgets.QLabel(SheetImportDialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.range_label.sizePolicy().hasHeightForWidth())
        self.range_label.setSizePolicy(sizePolicy)
        self.range_label.setMinimumSize(QtCore.QSize(45, 0))
        self.range_label.setMaximumSize(QtCore.QSize(45, 16777215))
        self.range_label.setObjectName("range_label")
        self.horizontalLayout_3.addWidget(self.range_label)
        self.range_linedit = QtWidgets.QLineEdit(SheetImportDialog)
        self.range_linedit.setText("")
        self.range_linedit.setObjectName("range_linedit")
        self.horizontalLayout_3.addWidget(self.range_linedit)
        self.verticalLayout.addLayout(self.horizontalLayout_3)
        spacerItem1 = QtWidgets.QSpacerItem(20, 7, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        self.verticalLayout.addItem(spacerItem1)
        self.horizontalLayout_5 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_5.setObjectName("horizontalLayout_5")
        self.help_button = QtWidgets.QPushButton(SheetImportDialog)
        self.help_button.setObjectName("help_button")
        self.horizontalLayout_5.addWidget(self.help_button)
        self.button_box = QtWidgets.QDialogButtonBox(SheetImportDialog)
        self.button_box.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.button_box.setObjectName("button_box")
        self.horizontalLayout_5.addWidget(self.button_box)
        self.verticalLayout.addLayout(self.horizontalLayout_5)

        self.retranslateUi(SheetImportDialog)
        QtCore.QMetaObject.connectSlotsByName(SheetImportDialog)

    def retranslateUi(self, SheetImportDialog):
        _translate = QtCore.QCoreApplication.translate
        SheetImportDialog.setWindowTitle(_translate("SheetImportDialog", "Import Excel Sheet"))
        self.instructions_label.setText(_translate("SheetImportDialog", "Click OK to replace the sheet data with the imported data or Cancel to go back."))
        self.file_label.setText(_translate("SheetImportDialog", "File Path:"))
        self.filepath_linedit.setPlaceholderText(_translate("SheetImportDialog", "path/to/excel"))
        self.browse_files_button.setText(_translate("SheetImportDialog", "..."))
        self.list_sheets_button.setText(_translate("SheetImportDialog", "List Sheets"))
        self.sheet_label.setText(_translate("SheetImportDialog", "Sheet:"))
        self.range_label.setText(_translate("SheetImportDialog", "Range:"))
        self.range_linedit.setPlaceholderText(_translate("SheetImportDialog", "Example: B1:E4 (optional; if empty: all sheet data)"))
        self.help_button.setText(_translate("SheetImportDialog", "Help"))

