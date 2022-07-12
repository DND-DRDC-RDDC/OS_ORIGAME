# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'edit_seed_dialog.ui'
#
# Created by: PyQt5 UI code generator 5.7
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_EditSeedDialog(object):
    def setupUi(self, EditSeedDialog):
        EditSeedDialog.setObjectName("EditSeedDialog")
        EditSeedDialog.resize(378, 200)
        EditSeedDialog.setMinimumSize(QtCore.QSize(378, 200))
        EditSeedDialog.setMaximumSize(QtCore.QSize(378, 200))
        self.verticalLayout = QtWidgets.QVBoxLayout(EditSeedDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.instructions_label = QtWidgets.QLabel(EditSeedDialog)
        self.instructions_label.setWordWrap(True)
        self.instructions_label.setObjectName("instructions_label")
        self.verticalLayout.addWidget(self.instructions_label)
        self.seed_linedit = QtWidgets.QLineEdit(EditSeedDialog)
        self.seed_linedit.setObjectName("seed_linedit")
        self.verticalLayout.addWidget(self.seed_linedit)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.generate_button = QtWidgets.QPushButton(EditSeedDialog)
        self.generate_button.setObjectName("generate_button")
        self.horizontalLayout.addWidget(self.generate_button)
        self.use_reset_seed_checkbox = QtWidgets.QCheckBox(EditSeedDialog)
        self.use_reset_seed_checkbox.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.use_reset_seed_checkbox.setObjectName("use_reset_seed_checkbox")
        self.horizontalLayout.addWidget(self.use_reset_seed_checkbox)
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.buttonBox = QtWidgets.QDialogButtonBox(EditSeedDialog)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(EditSeedDialog)
        self.buttonBox.accepted.connect(EditSeedDialog.accept)
        self.buttonBox.rejected.connect(EditSeedDialog.reject)
        QtCore.QMetaObject.connectSlotsByName(EditSeedDialog)

    def retranslateUi(self, EditSeedDialog):
        _translate = QtCore.QCoreApplication.translate
        EditSeedDialog.setWindowTitle(_translate("EditSeedDialog", "Edit Seed"))
        self.instructions_label.setText(_translate("EditSeedDialog", "Enter a seed value (integer < 1,000,000,000) for the scenario\'s random number generator. Click OK to apply it, or Cancel to abondon this operation."))
        self.generate_button.setText(_translate("EditSeedDialog", "Generate"))
        self.use_reset_seed_checkbox.setText(_translate("EditSeedDialog", "Use Reset Seed:"))

