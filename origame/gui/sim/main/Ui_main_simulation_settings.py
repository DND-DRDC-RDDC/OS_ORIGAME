# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\origame\gui\sim\main\ui_files\main_simulation_settings.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_MainSimulationSettingsDialog(object):
    def setupUi(self, MainSimulationSettingsDialog):
        MainSimulationSettingsDialog.setObjectName("MainSimulationSettingsDialog")
        MainSimulationSettingsDialog.resize(516, 337)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(MainSimulationSettingsDialog.sizePolicy().hasHeightForWidth())
        MainSimulationSettingsDialog.setSizePolicy(sizePolicy)
        MainSimulationSettingsDialog.setMaximumSize(QtCore.QSize(516, 16777215))
        self.verticalLayout = QtWidgets.QVBoxLayout(MainSimulationSettingsDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.left_vertical_layout = QtWidgets.QVBoxLayout()
        self.left_vertical_layout.setObjectName("left_vertical_layout")
        self.groupBox = QtWidgets.QGroupBox(MainSimulationSettingsDialog)
        self.groupBox.setObjectName("groupBox")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.groupBox)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.label = QtWidgets.QLabel(self.groupBox)
        self.label.setObjectName("label")
        self.horizontalLayout_3.addWidget(self.label)
        self.variant_num_spinbox = QtWidgets.QSpinBox(self.groupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.variant_num_spinbox.sizePolicy().hasHeightForWidth())
        self.variant_num_spinbox.setSizePolicy(sizePolicy)
        self.variant_num_spinbox.setMaximumSize(QtCore.QSize(70, 16777215))
        self.variant_num_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.variant_num_spinbox.setMinimum(1)
        self.variant_num_spinbox.setMaximum(999999999)
        self.variant_num_spinbox.setProperty("value", 1)
        self.variant_num_spinbox.setObjectName("variant_num_spinbox")
        self.horizontalLayout_3.addWidget(self.variant_num_spinbox)
        self.verticalLayout_2.addLayout(self.horizontalLayout_3)
        self.horizontalLayout_4 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        self.label_2 = QtWidgets.QLabel(self.groupBox)
        self.label_2.setObjectName("label_2")
        self.horizontalLayout_4.addWidget(self.label_2)
        self.replic_num_spinbox = QtWidgets.QSpinBox(self.groupBox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.replic_num_spinbox.sizePolicy().hasHeightForWidth())
        self.replic_num_spinbox.setSizePolicy(sizePolicy)
        self.replic_num_spinbox.setMaximumSize(QtCore.QSize(70, 16777215))
        self.replic_num_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.replic_num_spinbox.setMinimum(1)
        self.replic_num_spinbox.setMaximum(999999999)
        self.replic_num_spinbox.setProperty("value", 1)
        self.replic_num_spinbox.setObjectName("replic_num_spinbox")
        self.horizontalLayout_4.addWidget(self.replic_num_spinbox)
        self.verticalLayout_2.addLayout(self.horizontalLayout_4)
        self.left_vertical_layout.addWidget(self.groupBox)
        self.reset_seed_layout = QtWidgets.QVBoxLayout()
        self.reset_seed_layout.setObjectName("reset_seed_layout")
        self.left_vertical_layout.addLayout(self.reset_seed_layout)
        self.groupBox_3 = QtWidgets.QGroupBox(MainSimulationSettingsDialog)
        self.groupBox_3.setObjectName("groupBox_3")
        self.verticalLayout_3 = QtWidgets.QVBoxLayout(self.groupBox_3)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.horizontalLayout_5 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_5.setObjectName("horizontalLayout_5")
        self.label_3 = QtWidgets.QLabel(self.groupBox_3)
        self.label_3.setObjectName("label_3")
        self.horizontalLayout_5.addWidget(self.label_3)
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout_5.addItem(spacerItem)
        self.time_mode_combobox = QtWidgets.QComboBox(self.groupBox_3)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.time_mode_combobox.sizePolicy().hasHeightForWidth())
        self.time_mode_combobox.setSizePolicy(sizePolicy)
        self.time_mode_combobox.setMinimumSize(QtCore.QSize(100, 0))
        self.time_mode_combobox.setObjectName("time_mode_combobox")
        self.time_mode_combobox.addItem("")
        self.time_mode_combobox.addItem("")
        self.horizontalLayout_5.addWidget(self.time_mode_combobox)
        self.verticalLayout_3.addLayout(self.horizontalLayout_5)
        self.scale_realtime_groupbox = QtWidgets.QGroupBox(self.groupBox_3)
        self.scale_realtime_groupbox.setObjectName("scale_realtime_groupbox")
        self.verticalLayout_4 = QtWidgets.QVBoxLayout(self.scale_realtime_groupbox)
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.horizontalLayout_6 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_6.setObjectName("horizontalLayout_6")
        self.label_4 = QtWidgets.QLabel(self.scale_realtime_groupbox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_4.sizePolicy().hasHeightForWidth())
        self.label_4.setSizePolicy(sizePolicy)
        self.label_4.setMinimumSize(QtCore.QSize(78, 0))
        self.label_4.setMaximumSize(QtCore.QSize(78, 16777215))
        self.label_4.setObjectName("label_4")
        self.horizontalLayout_6.addWidget(self.label_4)
        self.label_5 = QtWidgets.QLabel(self.scale_realtime_groupbox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_5.sizePolicy().hasHeightForWidth())
        self.label_5.setSizePolicy(sizePolicy)
        self.label_5.setMinimumSize(QtCore.QSize(5, 0))
        self.label_5.setObjectName("label_5")
        self.horizontalLayout_6.addWidget(self.label_5)
        self.label_6 = QtWidgets.QLabel(self.scale_realtime_groupbox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_6.sizePolicy().hasHeightForWidth())
        self.label_6.setSizePolicy(sizePolicy)
        self.label_6.setMinimumSize(QtCore.QSize(89, 0))
        self.label_6.setObjectName("label_6")
        self.horizontalLayout_6.addWidget(self.label_6)
        spacerItem1 = QtWidgets.QSpacerItem(60, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout_6.addItem(spacerItem1)
        self.verticalLayout_4.addLayout(self.horizontalLayout_6)
        self.horizontalLayout_7 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_7.setObjectName("horizontalLayout_7")
        self.real_time_ratio_spinbox = QtWidgets.QSpinBox(self.scale_realtime_groupbox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.real_time_ratio_spinbox.sizePolicy().hasHeightForWidth())
        self.real_time_ratio_spinbox.setSizePolicy(sizePolicy)
        self.real_time_ratio_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.real_time_ratio_spinbox.setMinimum(1)
        self.real_time_ratio_spinbox.setMaximum(999999999)
        self.real_time_ratio_spinbox.setObjectName("real_time_ratio_spinbox")
        self.horizontalLayout_7.addWidget(self.real_time_ratio_spinbox)
        self.label_7 = QtWidgets.QLabel(self.scale_realtime_groupbox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_7.sizePolicy().hasHeightForWidth())
        self.label_7.setSizePolicy(sizePolicy)
        self.label_7.setObjectName("label_7")
        self.horizontalLayout_7.addWidget(self.label_7)
        self.sim_time_ratio_spinbox = QtWidgets.QSpinBox(self.scale_realtime_groupbox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.sim_time_ratio_spinbox.sizePolicy().hasHeightForWidth())
        self.sim_time_ratio_spinbox.setSizePolicy(sizePolicy)
        self.sim_time_ratio_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.sim_time_ratio_spinbox.setMinimum(1)
        self.sim_time_ratio_spinbox.setMaximum(999999999)
        self.sim_time_ratio_spinbox.setObjectName("sim_time_ratio_spinbox")
        self.horizontalLayout_7.addWidget(self.sim_time_ratio_spinbox)
        spacerItem2 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout_7.addItem(spacerItem2)
        self.verticalLayout_4.addLayout(self.horizontalLayout_7)
        self.verticalLayout_3.addWidget(self.scale_realtime_groupbox)
        self.left_vertical_layout.addWidget(self.groupBox_3)
        spacerItem3 = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.left_vertical_layout.addItem(spacerItem3)
        self.horizontalLayout_2.addLayout(self.left_vertical_layout)
        self.right_vertical_layout = QtWidgets.QVBoxLayout()
        self.right_vertical_layout.setObjectName("right_vertical_layout")
        self.horizontalLayout_2.addLayout(self.right_vertical_layout)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setContentsMargins(-1, -1, -1, 0)
        self.horizontalLayout.setSpacing(5)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.help_button = QtWidgets.QPushButton(MainSimulationSettingsDialog)
        self.help_button.setObjectName("help_button")
        self.horizontalLayout.addWidget(self.help_button)
        self.save_button = QtWidgets.QPushButton(MainSimulationSettingsDialog)
        self.save_button.setObjectName("save_button")
        self.horizontalLayout.addWidget(self.save_button)
        self.load_button = QtWidgets.QPushButton(MainSimulationSettingsDialog)
        self.load_button.setObjectName("load_button")
        self.horizontalLayout.addWidget(self.load_button)
        spacerItem4 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem4)
        self.button_box = QtWidgets.QDialogButtonBox(MainSimulationSettingsDialog)
        self.button_box.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.button_box.setObjectName("button_box")
        self.horizontalLayout.addWidget(self.button_box)
        self.apply_button = QtWidgets.QPushButton(MainSimulationSettingsDialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.apply_button.sizePolicy().hasHeightForWidth())
        self.apply_button.setSizePolicy(sizePolicy)
        self.apply_button.setMinimumSize(QtCore.QSize(0, 0))
        self.apply_button.setMaximumSize(QtCore.QSize(50, 16777215))
        self.apply_button.setObjectName("apply_button")
        self.horizontalLayout.addWidget(self.apply_button)
        self.verticalLayout.addLayout(self.horizontalLayout)
        spacerItem5 = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem5)

        self.retranslateUi(MainSimulationSettingsDialog)
        self.button_box.accepted.connect(MainSimulationSettingsDialog.accept) # type: ignore
        self.button_box.rejected.connect(MainSimulationSettingsDialog.reject) # type: ignore
        QtCore.QMetaObject.connectSlotsByName(MainSimulationSettingsDialog)

    def retranslateUi(self, MainSimulationSettingsDialog):
        _translate = QtCore.QCoreApplication.translate
        MainSimulationSettingsDialog.setWindowTitle(_translate("MainSimulationSettingsDialog", "Main Simulation Settings"))
        self.groupBox.setTitle(_translate("MainSimulationSettingsDialog", "Replication info"))
        self.label.setText(_translate("MainSimulationSettingsDialog", "Variant #"))
        self.label_2.setText(_translate("MainSimulationSettingsDialog", "Replication #"))
        self.groupBox_3.setTitle(_translate("MainSimulationSettingsDialog", "Time"))
        self.label_3.setText(_translate("MainSimulationSettingsDialog", "Mode"))
        self.time_mode_combobox.setItemText(0, _translate("MainSimulationSettingsDialog", "Real time"))
        self.time_mode_combobox.setItemText(1, _translate("MainSimulationSettingsDialog", "Immediate"))
        self.scale_realtime_groupbox.setTitle(_translate("MainSimulationSettingsDialog", "Scaled real time ratio"))
        self.label_4.setText(_translate("MainSimulationSettingsDialog", "Real time"))
        self.label_5.setText(_translate("MainSimulationSettingsDialog", ":"))
        self.label_6.setText(_translate("MainSimulationSettingsDialog", "Simulation time"))
        self.label_7.setText(_translate("MainSimulationSettingsDialog", ":"))
        self.help_button.setText(_translate("MainSimulationSettingsDialog", "Help"))
        self.save_button.setText(_translate("MainSimulationSettingsDialog", "Save..."))
        self.load_button.setText(_translate("MainSimulationSettingsDialog", "Load..."))
        self.apply_button.setText(_translate("MainSimulationSettingsDialog", "Apply"))

