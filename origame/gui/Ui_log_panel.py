# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\origame\gui\ui_files\log_panel.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_LogPanel(object):
    def setupUi(self, LogPanel):
        LogPanel.setObjectName("LogPanel")
        LogPanel.resize(808, 330)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout(LogPanel)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.log_record_display = QtWidgets.QPlainTextEdit(LogPanel)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.log_record_display.sizePolicy().hasHeightForWidth())
        self.log_record_display.setSizePolicy(sizePolicy)
        self.log_record_display.setReadOnly(True)
        self.log_record_display.setObjectName("log_record_display")
        self.horizontalLayout_2.addWidget(self.log_record_display)
        self.toggle_options_button = QtWidgets.QToolButton(LogPanel)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.toggle_options_button.sizePolicy().hasHeightForWidth())
        self.toggle_options_button.setSizePolicy(sizePolicy)
        self.toggle_options_button.setAutoRaise(False)
        self.toggle_options_button.setArrowType(QtCore.Qt.RightArrow)
        self.toggle_options_button.setObjectName("toggle_options_button")
        self.horizontalLayout_2.addWidget(self.toggle_options_button)
        self.options_panel = QtWidgets.QWidget(LogPanel)
        self.options_panel.setObjectName("options_panel")
        self.verticalLayout = QtWidgets.QVBoxLayout(self.options_panel)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.filter_group = QtWidgets.QGroupBox(self.options_panel)
        self.filter_group.setMinimumSize(QtCore.QSize(0, 0))
        self.filter_group.setObjectName("filter_group")
        self.verticalLayout_5 = QtWidgets.QVBoxLayout(self.filter_group)
        self.verticalLayout_5.setContentsMargins(5, -1, 5, -1)
        self.verticalLayout_5.setObjectName("verticalLayout_5")
        self.gridLayout_filter = QtWidgets.QGridLayout()
        self.gridLayout_filter.setContentsMargins(7, 0, 0, -1)
        self.gridLayout_filter.setObjectName("gridLayout_filter")
        self.label_print_logs = QtWidgets.QLabel(self.filter_group)
        self.label_print_logs.setObjectName("label_print_logs")
        self.gridLayout_filter.addWidget(self.label_print_logs, 6, 0, 1, 1)
        self.label_info_logs = QtWidgets.QLabel(self.filter_group)
        self.label_info_logs.setObjectName("label_info_logs")
        self.gridLayout_filter.addWidget(self.label_info_logs, 5, 0, 1, 1)
        self.label_error_logs = QtWidgets.QLabel(self.filter_group)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_error_logs.sizePolicy().hasHeightForWidth())
        self.label_error_logs.setSizePolicy(sizePolicy)
        self.label_error_logs.setObjectName("label_error_logs")
        self.gridLayout_filter.addWidget(self.label_error_logs, 3, 0, 1, 1)
        self.label_warning_logs = QtWidgets.QLabel(self.filter_group)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_warning_logs.sizePolicy().hasHeightForWidth())
        self.label_warning_logs.setSizePolicy(sizePolicy)
        self.label_warning_logs.setObjectName("label_warning_logs")
        self.gridLayout_filter.addWidget(self.label_warning_logs, 4, 0, 1, 1)
        self.checkbox_user_print_logs = QtWidgets.QCheckBox(self.filter_group)
        self.checkbox_user_print_logs.setText("")
        self.checkbox_user_print_logs.setChecked(True)
        self.checkbox_user_print_logs.setObjectName("checkbox_user_print_logs")
        self.gridLayout_filter.addWidget(self.checkbox_user_print_logs, 6, 2, 1, 1)
        self.checkbox_system_critical_logs = QtWidgets.QCheckBox(self.filter_group)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.checkbox_system_critical_logs.sizePolicy().hasHeightForWidth())
        self.checkbox_system_critical_logs.setSizePolicy(sizePolicy)
        self.checkbox_system_critical_logs.setLayoutDirection(QtCore.Qt.LeftToRight)
        self.checkbox_system_critical_logs.setAutoFillBackground(False)
        self.checkbox_system_critical_logs.setText("")
        self.checkbox_system_critical_logs.setChecked(True)
        self.checkbox_system_critical_logs.setObjectName("checkbox_system_critical_logs")
        self.gridLayout_filter.addWidget(self.checkbox_system_critical_logs, 2, 1, 1, 1)
        self.checkbox_user_critical_logs = QtWidgets.QCheckBox(self.filter_group)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.checkbox_user_critical_logs.sizePolicy().hasHeightForWidth())
        self.checkbox_user_critical_logs.setSizePolicy(sizePolicy)
        self.checkbox_user_critical_logs.setText("")
        self.checkbox_user_critical_logs.setChecked(True)
        self.checkbox_user_critical_logs.setObjectName("checkbox_user_critical_logs")
        self.gridLayout_filter.addWidget(self.checkbox_user_critical_logs, 2, 2, 1, 1)
        self.label_critical_logs = QtWidgets.QLabel(self.filter_group)
        self.label_critical_logs.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_critical_logs.sizePolicy().hasHeightForWidth())
        self.label_critical_logs.setSizePolicy(sizePolicy)
        self.label_critical_logs.setObjectName("label_critical_logs")
        self.gridLayout_filter.addWidget(self.label_critical_logs, 2, 0, 1, 1)
        self.label_filter_system = QtWidgets.QLabel(self.filter_group)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_filter_system.sizePolicy().hasHeightForWidth())
        self.label_filter_system.setSizePolicy(sizePolicy)
        self.label_filter_system.setMinimumSize(QtCore.QSize(50, 0))
        self.label_filter_system.setObjectName("label_filter_system")
        self.gridLayout_filter.addWidget(self.label_filter_system, 1, 1, 1, 1)
        self.checkbox_system_warning_logs = QtWidgets.QCheckBox(self.filter_group)
        self.checkbox_system_warning_logs.setText("")
        self.checkbox_system_warning_logs.setChecked(True)
        self.checkbox_system_warning_logs.setObjectName("checkbox_system_warning_logs")
        self.gridLayout_filter.addWidget(self.checkbox_system_warning_logs, 4, 1, 1, 1)
        self.checkbox_user_error_logs = QtWidgets.QCheckBox(self.filter_group)
        self.checkbox_user_error_logs.setText("")
        self.checkbox_user_error_logs.setChecked(True)
        self.checkbox_user_error_logs.setObjectName("checkbox_user_error_logs")
        self.gridLayout_filter.addWidget(self.checkbox_user_error_logs, 3, 2, 1, 1)
        self.checkbox_user_warning_logs = QtWidgets.QCheckBox(self.filter_group)
        self.checkbox_user_warning_logs.setText("")
        self.checkbox_user_warning_logs.setChecked(True)
        self.checkbox_user_warning_logs.setObjectName("checkbox_user_warning_logs")
        self.gridLayout_filter.addWidget(self.checkbox_user_warning_logs, 4, 2, 1, 1)
        self.checkbox_system_error_logs = QtWidgets.QCheckBox(self.filter_group)
        self.checkbox_system_error_logs.setText("")
        self.checkbox_system_error_logs.setChecked(True)
        self.checkbox_system_error_logs.setObjectName("checkbox_system_error_logs")
        self.gridLayout_filter.addWidget(self.checkbox_system_error_logs, 3, 1, 1, 1)
        self.checkbox_user_info_logs = QtWidgets.QCheckBox(self.filter_group)
        self.checkbox_user_info_logs.setText("")
        self.checkbox_user_info_logs.setChecked(True)
        self.checkbox_user_info_logs.setObjectName("checkbox_user_info_logs")
        self.gridLayout_filter.addWidget(self.checkbox_user_info_logs, 5, 2, 1, 1)
        self.checkbox_system_info_logs = QtWidgets.QCheckBox(self.filter_group)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.checkbox_system_info_logs.sizePolicy().hasHeightForWidth())
        self.checkbox_system_info_logs.setSizePolicy(sizePolicy)
        self.checkbox_system_info_logs.setText("")
        self.checkbox_system_info_logs.setChecked(True)
        self.checkbox_system_info_logs.setObjectName("checkbox_system_info_logs")
        self.gridLayout_filter.addWidget(self.checkbox_system_info_logs, 5, 1, 1, 1)
        self.label_filter_user = QtWidgets.QLabel(self.filter_group)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_filter_user.sizePolicy().hasHeightForWidth())
        self.label_filter_user.setSizePolicy(sizePolicy)
        self.label_filter_user.setMinimumSize(QtCore.QSize(0, 0))
        self.label_filter_user.setObjectName("label_filter_user")
        self.gridLayout_filter.addWidget(self.label_filter_user, 1, 2, 1, 1)
        self.checkbox_system_debug_logs = QtWidgets.QCheckBox(self.filter_group)
        self.checkbox_system_debug_logs.setEnabled(False)
        self.checkbox_system_debug_logs.setText("")
        self.checkbox_system_debug_logs.setObjectName("checkbox_system_debug_logs")
        self.gridLayout_filter.addWidget(self.checkbox_system_debug_logs, 6, 1, 1, 1)
        self.gridLayout_filter.setColumnMinimumWidth(0, 60)
        self.verticalLayout_5.addLayout(self.gridLayout_filter)
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.save_button = QtWidgets.QPushButton(self.filter_group)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.save_button.sizePolicy().hasHeightForWidth())
        self.save_button.setSizePolicy(sizePolicy)
        self.save_button.setMinimumSize(QtCore.QSize(20, 0))
        self.save_button.setObjectName("save_button")
        self.horizontalLayout_3.addWidget(self.save_button)
        self.hide_prev_button = QtWidgets.QPushButton(self.filter_group)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(2)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.hide_prev_button.sizePolicy().hasHeightForWidth())
        self.hide_prev_button.setSizePolicy(sizePolicy)
        self.hide_prev_button.setObjectName("hide_prev_button")
        self.horizontalLayout_3.addWidget(self.hide_prev_button)
        self.verticalLayout_5.addLayout(self.horizontalLayout_3)
        spacerItem = QtWidgets.QSpacerItem(20, 488, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.verticalLayout_5.addItem(spacerItem)
        self.verticalLayout.addWidget(self.filter_group)
        self.horizontalLayout_2.addWidget(self.options_panel)

        self.retranslateUi(LogPanel)
        QtCore.QMetaObject.connectSlotsByName(LogPanel)
        LogPanel.setTabOrder(self.log_record_display, self.checkbox_system_critical_logs)
        LogPanel.setTabOrder(self.checkbox_system_critical_logs, self.checkbox_user_critical_logs)
        LogPanel.setTabOrder(self.checkbox_user_critical_logs, self.checkbox_system_error_logs)
        LogPanel.setTabOrder(self.checkbox_system_error_logs, self.checkbox_user_error_logs)
        LogPanel.setTabOrder(self.checkbox_user_error_logs, self.checkbox_system_warning_logs)
        LogPanel.setTabOrder(self.checkbox_system_warning_logs, self.checkbox_user_warning_logs)
        LogPanel.setTabOrder(self.checkbox_user_warning_logs, self.checkbox_system_info_logs)
        LogPanel.setTabOrder(self.checkbox_system_info_logs, self.checkbox_user_info_logs)
        LogPanel.setTabOrder(self.checkbox_user_info_logs, self.checkbox_user_print_logs)

    def retranslateUi(self, LogPanel):
        _translate = QtCore.QCoreApplication.translate
        LogPanel.setWindowTitle(_translate("LogPanel", "Form"))
        self.log_record_display.setPlainText(_translate("LogPanel", "sys: 2014/08/22 13:22:01: Error: This is a system error message\n"
"sys: 2014/08/22 13:22:02: Warning: This is a system warning \n"
"user: 2014/08/22 13:22:03: Information: This is an information user message\n"
""))
        self.toggle_options_button.setToolTip(_translate("LogPanel", "Toggle Options Panel"))
        self.toggle_options_button.setText(_translate("LogPanel", "..."))
        self.filter_group.setTitle(_translate("LogPanel", "Filter"))
        self.label_print_logs.setText(_translate("LogPanel", "Print"))
        self.label_info_logs.setText(_translate("LogPanel", "Info"))
        self.label_error_logs.setText(_translate("LogPanel", "Error"))
        self.label_warning_logs.setText(_translate("LogPanel", "Warning"))
        self.label_critical_logs.setText(_translate("LogPanel", "Critical"))
        self.label_filter_system.setText(_translate("LogPanel", "System:"))
        self.label_filter_user.setText(_translate("LogPanel", "User:"))
        self.save_button.setToolTip(_translate("LogPanel", "Save all the log or a selected part of the log into a file"))
        self.save_button.setText(_translate("LogPanel", "Save..."))
        self.hide_prev_button.setToolTip(_translate("LogPanel", "Toggle hiding of log messages that precede the marked log message"))
        self.hide_prev_button.setText(_translate("LogPanel", "Hide Previous"))
