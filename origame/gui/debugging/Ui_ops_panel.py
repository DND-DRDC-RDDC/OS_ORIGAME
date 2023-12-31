# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\origame\gui\debugging\ui_files\ops_panel.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_DebugWidget(object):
    def setupUi(self, DebugWidget):
        DebugWidget.setObjectName("DebugWidget")
        DebugWidget.resize(498, 387)
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(DebugWidget)
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.groupBox = QtWidgets.QGroupBox(DebugWidget)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.groupBox.sizePolicy().hasHeightForWidth())
        self.groupBox.setSizePolicy(sizePolicy)
        self.groupBox.setObjectName("groupBox")
        self.verticalLayout_4 = QtWidgets.QVBoxLayout(self.groupBox)
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.breakpoint_on_off_button = QtWidgets.QPushButton(self.groupBox)
        self.breakpoint_on_off_button.setEnabled(False)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.breakpoint_on_off_button.sizePolicy().hasHeightForWidth())
        self.breakpoint_on_off_button.setSizePolicy(sizePolicy)
        self.breakpoint_on_off_button.setMinimumSize(QtCore.QSize(0, 0))
        self.breakpoint_on_off_button.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)
        self.breakpoint_on_off_button.setLayoutDirection(QtCore.Qt.LeftToRight)
        self.breakpoint_on_off_button.setIconSize(QtCore.QSize(0, 0))
        self.breakpoint_on_off_button.setObjectName("breakpoint_on_off_button")
        self.verticalLayout_4.addWidget(self.breakpoint_on_off_button)
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setSizeConstraint(QtWidgets.QLayout.SetDefaultConstraint)
        self.horizontalLayout_2.setSpacing(6)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.step_button = QtWidgets.QPushButton(self.groupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.step_button.sizePolicy().hasHeightForWidth())
        self.step_button.setSizePolicy(sizePolicy)
        self.step_button.setMaximumSize(QtCore.QSize(16777215, 16777215))
        font = QtGui.QFont()
        font.setPointSize(7)
        self.step_button.setFont(font)
        self.step_button.setObjectName("step_button")
        self.horizontalLayout_2.addWidget(self.step_button)
        self.step_into_button = QtWidgets.QPushButton(self.groupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.step_into_button.sizePolicy().hasHeightForWidth())
        self.step_into_button.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        font.setPointSize(7)
        self.step_into_button.setFont(font)
        self.step_into_button.setObjectName("step_into_button")
        self.horizontalLayout_2.addWidget(self.step_into_button)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setSpacing(6)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.continue_button = QtWidgets.QPushButton(self.groupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.continue_button.sizePolicy().hasHeightForWidth())
        self.continue_button.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        font.setPointSize(7)
        self.continue_button.setFont(font)
        self.continue_button.setObjectName("continue_button")
        self.horizontalLayout.addWidget(self.continue_button)
        self.stop_button = QtWidgets.QPushButton(self.groupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.stop_button.sizePolicy().hasHeightForWidth())
        self.stop_button.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        font.setPointSize(7)
        self.stop_button.setFont(font)
        self.stop_button.setObjectName("stop_button")
        self.horizontalLayout.addWidget(self.stop_button)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.horizontalLayout_3.addLayout(self.verticalLayout)
        self.verticalLayout_4.addLayout(self.horizontalLayout_3)
        self.verticalLayout_3 = QtWidgets.QVBoxLayout()
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.label = QtWidgets.QLabel(self.groupBox)
        self.label.setObjectName("label")
        self.verticalLayout_3.addWidget(self.label)
        self.local_variables_list = QtWidgets.QListWidget(self.groupBox)
        self.local_variables_list.setObjectName("local_variables_list")
        self.verticalLayout_3.addWidget(self.local_variables_list)
        self.verticalLayout_4.addLayout(self.verticalLayout_3)
        self.label_2 = QtWidgets.QLabel(self.groupBox)
        self.label_2.setObjectName("label_2")
        self.verticalLayout_4.addWidget(self.label_2)
        self.horizontalLayout_4 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        self.python_expression = QtWidgets.QLineEdit(self.groupBox)
        self.python_expression.setObjectName("python_expression")
        self.horizontalLayout_4.addWidget(self.python_expression)
        self.evaluate_button = QtWidgets.QPushButton(self.groupBox)
        self.evaluate_button.setMinimumSize(QtCore.QSize(75, 0))
        self.evaluate_button.setMaximumSize(QtCore.QSize(50, 16777215))
        self.evaluate_button.setObjectName("evaluate_button")
        self.horizontalLayout_4.addWidget(self.evaluate_button)
        self.verticalLayout_4.addLayout(self.horizontalLayout_4)
        self.label_3 = QtWidgets.QLabel(self.groupBox)
        self.label_3.setObjectName("label_3")
        self.verticalLayout_4.addWidget(self.label_3)
        self.expression_result_list = QtWidgets.QListWidget(self.groupBox)
        self.expression_result_list.setObjectName("expression_result_list")
        self.verticalLayout_4.addWidget(self.expression_result_list)
        self.verticalLayout_2.addWidget(self.groupBox)

        self.retranslateUi(DebugWidget)
        QtCore.QMetaObject.connectSlotsByName(DebugWidget)

    def retranslateUi(self, DebugWidget):
        _translate = QtCore.QCoreApplication.translate
        DebugWidget.setWindowTitle(_translate("DebugWidget", "Debug Operations"))
        self.groupBox.setTitle(_translate("DebugWidget", "Debug Operations"))
        self.breakpoint_on_off_button.setText(_translate("DebugWidget", "BP On/Off"))
        self.step_button.setText(_translate("DebugWidget", "Step"))
        self.step_into_button.setText(_translate("DebugWidget", "Step Into"))
        self.continue_button.setText(_translate("DebugWidget", "Continue"))
        self.stop_button.setText(_translate("DebugWidget", "Stop"))
        self.label.setText(_translate("DebugWidget", "Local Variables:"))
        self.label_2.setText(_translate("DebugWidget", "Python Expression:"))
        self.evaluate_button.setText(_translate("DebugWidget", "Evaluate"))
        self.label_3.setText(_translate("DebugWidget", "Expression Result:"))

