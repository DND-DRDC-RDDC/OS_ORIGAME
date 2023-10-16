# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\origame\gui\object_properties\ui_files\object_properties.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_ObjectPropertiesEditor(object):
    def setupUi(self, ObjectPropertiesEditor):
        ObjectPropertiesEditor.setObjectName("ObjectPropertiesEditor")
        ObjectPropertiesEditor.resize(373, 511)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(ObjectPropertiesEditor.sizePolicy().hasHeightForWidth())
        ObjectPropertiesEditor.setSizePolicy(sizePolicy)
        ObjectPropertiesEditor.setStyleSheet("QLineEdit:read-only {\n"
"    color: grey;\n"
"}")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(ObjectPropertiesEditor)
        self.verticalLayout_2.setContentsMargins(7, 7, 7, 7)
        self.verticalLayout_2.setSpacing(5)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.general_groupbox = QtWidgets.QGroupBox(ObjectPropertiesEditor)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Maximum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.general_groupbox.sizePolicy().hasHeightForWidth())
        self.general_groupbox.setSizePolicy(sizePolicy)
        self.general_groupbox.setMinimumSize(QtCore.QSize(0, 0))
        self.general_groupbox.setAlignment(QtCore.Qt.AlignLeading|QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter)
        self.general_groupbox.setObjectName("general_groupbox")
        self.gridLayout = QtWidgets.QGridLayout(self.general_groupbox)
        self.gridLayout.setObjectName("gridLayout")
        self.icon_display = QSvgWidget(self.general_groupbox)
        self.icon_display.setObjectName("icon_display")
        self.gridLayout.addWidget(self.icon_display, 0, 0, 1, 1)
        self.formLayout = QtWidgets.QFormLayout()
        self.formLayout.setContentsMargins(7, 5, -1, 5)
        self.formLayout.setHorizontalSpacing(0)
        self.formLayout.setObjectName("formLayout")
        self.part_type_label = QtWidgets.QLabel(self.general_groupbox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.part_type_label.sizePolicy().hasHeightForWidth())
        self.part_type_label.setSizePolicy(sizePolicy)
        self.part_type_label.setMinimumSize(QtCore.QSize(0, 0))
        self.part_type_label.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.part_type_label.setLayoutDirection(QtCore.Qt.LeftToRight)
        self.part_type_label.setAlignment(QtCore.Qt.AlignLeading|QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter)
        self.part_type_label.setObjectName("part_type_label")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.part_type_label)
        self.type_display = QtWidgets.QLineEdit(self.general_groupbox)
        self.type_display.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.type_display.sizePolicy().hasHeightForWidth())
        self.type_display.setSizePolicy(sizePolicy)
        self.type_display.setText("")
        self.type_display.setReadOnly(True)
        self.type_display.setObjectName("type_display")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.type_display)
        self.part_name_label = QtWidgets.QLabel(self.general_groupbox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.part_name_label.sizePolicy().hasHeightForWidth())
        self.part_name_label.setSizePolicy(sizePolicy)
        self.part_name_label.setMinimumSize(QtCore.QSize(0, 0))
        self.part_name_label.setMaximumSize(QtCore.QSize(80, 16777215))
        self.part_name_label.setObjectName("part_name_label")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.part_name_label)
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.id_line_edit = PartNameLineEdit(self.general_groupbox)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.id_line_edit.sizePolicy().hasHeightForWidth())
        self.id_line_edit.setSizePolicy(sizePolicy)
        self.id_line_edit.setText("")
        self.id_line_edit.setReadOnly(False)
        self.id_line_edit.setObjectName("id_line_edit")
        self.horizontalLayout_3.addWidget(self.id_line_edit)
        self.rename_link_button = QtWidgets.QToolButton(self.general_groupbox)
        self.rename_link_button.setObjectName("rename_link_button")
        self.horizontalLayout_3.addWidget(self.rename_link_button)
        self.formLayout.setLayout(1, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout_3)
        self.gridLayout.addLayout(self.formLayout, 0, 1, 1, 1)
        self.verticalLayout_2.addWidget(self.general_groupbox)
        self.part_group_box = QtWidgets.QGroupBox(ObjectPropertiesEditor)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.part_group_box.sizePolicy().hasHeightForWidth())
        self.part_group_box.setSizePolicy(sizePolicy)
        self.part_group_box.setObjectName("part_group_box")
        self.formLayout_2 = QtWidgets.QFormLayout(self.part_group_box)
        self.formLayout_2.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.formLayout_2.setObjectName("formLayout_2")
        self.label_4 = QtWidgets.QLabel(self.part_group_box)
        self.label_4.setObjectName("label_4")
        self.formLayout_2.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label_4)
        self.comment_label = QtWidgets.QLabel(self.part_group_box)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.comment_label.sizePolicy().hasHeightForWidth())
        self.comment_label.setSizePolicy(sizePolicy)
        self.comment_label.setObjectName("comment_label")
        self.formLayout_2.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.comment_label)
        self.comment_text_edit = CommentTextBox(self.part_group_box)
        self.comment_text_edit.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.comment_text_edit.sizePolicy().hasHeightForWidth())
        self.comment_text_edit.setSizePolicy(sizePolicy)
        self.comment_text_edit.setMinimumSize(QtCore.QSize(0, 0))
        self.comment_text_edit.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.comment_text_edit.setTabChangesFocus(True)
        self.comment_text_edit.setObjectName("comment_text_edit")
        self.formLayout_2.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.comment_text_edit)
        self.x_position_label = QtWidgets.QLabel(self.part_group_box)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.x_position_label.sizePolicy().hasHeightForWidth())
        self.x_position_label.setSizePolicy(sizePolicy)
        self.x_position_label.setMinimumSize(QtCore.QSize(0, 0))
        self.x_position_label.setObjectName("x_position_label")
        self.formLayout_2.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.x_position_label)
        self.y_position_label = QtWidgets.QLabel(self.part_group_box)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.y_position_label.sizePolicy().hasHeightForWidth())
        self.y_position_label.setSizePolicy(sizePolicy)
        self.y_position_label.setObjectName("y_position_label")
        self.formLayout_2.setWidget(3, QtWidgets.QFormLayout.LabelRole, self.y_position_label)
        self.x_part_pos_doublespinbox = QtWidgets.QDoubleSpinBox(self.part_group_box)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.x_part_pos_doublespinbox.sizePolicy().hasHeightForWidth())
        self.x_part_pos_doublespinbox.setSizePolicy(sizePolicy)
        self.x_part_pos_doublespinbox.setMinimumSize(QtCore.QSize(0, 0))
        self.x_part_pos_doublespinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.x_part_pos_doublespinbox.setMinimum(-63913200.0)
        self.x_part_pos_doublespinbox.setMaximum(63913200.0)
        self.x_part_pos_doublespinbox.setSingleStep(0.01)
        self.x_part_pos_doublespinbox.setObjectName("x_part_pos_doublespinbox")
        self.formLayout_2.setWidget(2, QtWidgets.QFormLayout.FieldRole, self.x_part_pos_doublespinbox)
        self.y_part_pos_doublespinbox = QtWidgets.QDoubleSpinBox(self.part_group_box)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.y_part_pos_doublespinbox.sizePolicy().hasHeightForWidth())
        self.y_part_pos_doublespinbox.setSizePolicy(sizePolicy)
        self.y_part_pos_doublespinbox.setMinimumSize(QtCore.QSize(0, 0))
        self.y_part_pos_doublespinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.y_part_pos_doublespinbox.setMinimum(-63913200.0)
        self.y_part_pos_doublespinbox.setMaximum(63913200.0)
        self.y_part_pos_doublespinbox.setSingleStep(0.01)
        self.y_part_pos_doublespinbox.setObjectName("y_part_pos_doublespinbox")
        self.formLayout_2.setWidget(3, QtWidgets.QFormLayout.FieldRole, self.y_part_pos_doublespinbox)
        self.ifx_level_combobox = QtWidgets.QComboBox(self.part_group_box)
        self.ifx_level_combobox.setObjectName("ifx_level_combobox")
        self.ifx_level_combobox.addItem("")
        self.formLayout_2.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.ifx_level_combobox)
        self.verticalLayout_2.addWidget(self.part_group_box)
        self.waypoint_group_box = QtWidgets.QGroupBox(ObjectPropertiesEditor)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Maximum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.waypoint_group_box.sizePolicy().hasHeightForWidth())
        self.waypoint_group_box.setSizePolicy(sizePolicy)
        self.waypoint_group_box.setObjectName("waypoint_group_box")
        self.formLayout_3 = QtWidgets.QFormLayout(self.waypoint_group_box)
        self.formLayout_3.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.formLayout_3.setObjectName("formLayout_3")
        self.label_5 = QtWidgets.QLabel(self.waypoint_group_box)
        self.label_5.setMinimumSize(QtCore.QSize(89, 0))
        self.label_5.setObjectName("label_5")
        self.formLayout_3.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.label_5)
        self.x_waypoint_pos_doublespinbox = QtWidgets.QDoubleSpinBox(self.waypoint_group_box)
        self.x_waypoint_pos_doublespinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.x_waypoint_pos_doublespinbox.setMinimum(-63913200.0)
        self.x_waypoint_pos_doublespinbox.setMaximum(63913200.0)
        self.x_waypoint_pos_doublespinbox.setSingleStep(0.01)
        self.x_waypoint_pos_doublespinbox.setObjectName("x_waypoint_pos_doublespinbox")
        self.formLayout_3.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.x_waypoint_pos_doublespinbox)
        self.label_6 = QtWidgets.QLabel(self.waypoint_group_box)
        self.label_6.setObjectName("label_6")
        self.formLayout_3.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.label_6)
        self.y_waypoint_pos_doublespinbox = QtWidgets.QDoubleSpinBox(self.waypoint_group_box)
        self.y_waypoint_pos_doublespinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.y_waypoint_pos_doublespinbox.setMinimum(-63913200.0)
        self.y_waypoint_pos_doublespinbox.setMaximum(63913200.0)
        self.y_waypoint_pos_doublespinbox.setSingleStep(0.01)
        self.y_waypoint_pos_doublespinbox.setObjectName("y_waypoint_pos_doublespinbox")
        self.formLayout_3.setWidget(2, QtWidgets.QFormLayout.FieldRole, self.y_waypoint_pos_doublespinbox)
        self.verticalLayout_2.addWidget(self.waypoint_group_box)
        self.link_group_box = QtWidgets.QGroupBox(ObjectPropertiesEditor)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.link_group_box.sizePolicy().hasHeightForWidth())
        self.link_group_box.setSizePolicy(sizePolicy)
        self.link_group_box.setObjectName("link_group_box")
        self.formLayout_4 = QtWidgets.QFormLayout(self.link_group_box)
        self.formLayout_4.setObjectName("formLayout_4")
        self.label = QtWidgets.QLabel(self.link_group_box)
        self.label.setObjectName("label")
        self.formLayout_4.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label)
        self.declutter_checkbox = QtWidgets.QCheckBox(self.link_group_box)
        self.declutter_checkbox.setLayoutDirection(QtCore.Qt.LeftToRight)
        self.declutter_checkbox.setText("")
        self.declutter_checkbox.setObjectName("declutter_checkbox")
        self.formLayout_4.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.declutter_checkbox)
        self.label_2 = QtWidgets.QLabel(self.link_group_box)
        self.label_2.setObjectName("label_2")
        self.formLayout_4.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.label_2)
        self.label_8 = QtWidgets.QLabel(self.link_group_box)
        self.label_8.setObjectName("label_8")
        self.formLayout_4.setWidget(3, QtWidgets.QFormLayout.LabelRole, self.label_8)
        self.waypoint_number_spinbox = QtWidgets.QSpinBox(self.link_group_box)
        self.waypoint_number_spinbox.setReadOnly(True)
        self.waypoint_number_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.waypoint_number_spinbox.setObjectName("waypoint_number_spinbox")
        self.formLayout_4.setWidget(3, QtWidgets.QFormLayout.FieldRole, self.waypoint_number_spinbox)
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label_3 = QtWidgets.QLabel(self.link_group_box)
        self.label_3.setObjectName("label_3")
        self.horizontalLayout.addWidget(self.label_3)
        self.source_type_line_edit = QtWidgets.QLineEdit(self.link_group_box)
        self.source_type_line_edit.setReadOnly(True)
        self.source_type_line_edit.setObjectName("source_type_line_edit")
        self.horizontalLayout.addWidget(self.source_type_line_edit)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.label_7 = QtWidgets.QLabel(self.link_group_box)
        self.label_7.setObjectName("label_7")
        self.horizontalLayout_2.addWidget(self.label_7)
        self.target_type_line_edit = QtWidgets.QLineEdit(self.link_group_box)
        self.target_type_line_edit.setReadOnly(True)
        self.target_type_line_edit.setObjectName("target_type_line_edit")
        self.horizontalLayout_2.addWidget(self.target_type_line_edit)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.formLayout_4.setLayout(1, QtWidgets.QFormLayout.FieldRole, self.verticalLayout)
        self.verticalLayout_2.addWidget(self.link_group_box)

        self.retranslateUi(ObjectPropertiesEditor)
        QtCore.QMetaObject.connectSlotsByName(ObjectPropertiesEditor)
        ObjectPropertiesEditor.setTabOrder(self.type_display, self.id_line_edit)

    def retranslateUi(self, ObjectPropertiesEditor):
        _translate = QtCore.QCoreApplication.translate
        ObjectPropertiesEditor.setWindowTitle(_translate("ObjectPropertiesEditor", "Object Properties"))
        self.general_groupbox.setTitle(_translate("ObjectPropertiesEditor", "General"))
        self.part_type_label.setText(_translate("ObjectPropertiesEditor", "Type:"))
        self.type_display.setToolTip(_translate("ObjectPropertiesEditor", "Displays the selected parts type"))
        self.part_name_label.setText(_translate("ObjectPropertiesEditor", "Name:    "))
        self.id_line_edit.setToolTip(_translate("ObjectPropertiesEditor", "Edit the part name"))
        self.rename_link_button.setText(_translate("ObjectPropertiesEditor", "..."))
        self.part_group_box.setTitle(_translate("ObjectPropertiesEditor", "Part"))
        self.label_4.setText(_translate("ObjectPropertiesEditor", "Interface Level:"))
        self.comment_label.setText(_translate("ObjectPropertiesEditor", "Comment:"))
        self.comment_text_edit.setToolTip(_translate("ObjectPropertiesEditor", "Comments for this part"))
        self.x_position_label.setText(_translate("ObjectPropertiesEditor", "X:"))
        self.y_position_label.setText(_translate("ObjectPropertiesEditor", "Y:"))
        self.x_part_pos_doublespinbox.setToolTip(_translate("ObjectPropertiesEditor", "Set the part x-position in the 2D view"))
        self.y_part_pos_doublespinbox.setToolTip(_translate("ObjectPropertiesEditor", "Set the part y-position in the 2D view"))
        self.ifx_level_combobox.setCurrentText(_translate("ObjectPropertiesEditor", "0"))
        self.ifx_level_combobox.setItemText(0, _translate("ObjectPropertiesEditor", "0"))
        self.waypoint_group_box.setTitle(_translate("ObjectPropertiesEditor", "Waypoint"))
        self.label_5.setText(_translate("ObjectPropertiesEditor", "X:"))
        self.label_6.setText(_translate("ObjectPropertiesEditor", "Y:"))
        self.link_group_box.setTitle(_translate("ObjectPropertiesEditor", "Link"))
        self.label.setText(_translate("ObjectPropertiesEditor", "Declutter mode:"))
        self.label_2.setText(_translate("ObjectPropertiesEditor", "Part type:"))
        self.label_8.setText(_translate("ObjectPropertiesEditor", "Waypoints:"))
        self.label_3.setText(_translate("ObjectPropertiesEditor", "Source"))
        self.label_7.setText(_translate("ObjectPropertiesEditor", "Target"))
from .object_properties_custom_widgets import CommentTextBox, PartNameLineEdit
from PyQt5.QtSvg import QSvgWidget
