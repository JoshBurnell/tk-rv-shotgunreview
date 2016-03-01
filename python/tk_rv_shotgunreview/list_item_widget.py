# Copyright (c) 2016 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

from collections import OrderedDict

from .ui.list_item_widget import Ui_ListItemWidget

import tank

from tank.platform.qt import QtCore, QtGui
from .qtwidgets import ShotgunFieldManager

class ListItemWidget(QtGui.QWidget):
    """
    Simple list *item* widget which hosts a thumbnail, plus any requested
    entity fields in a layout to the right of the thumbnail.

    :ivar show_labels:      Whether to show entity field labels when the
                            widget is drawn.
    :vartype show_labels:   bool
    :ivar field_manager:    The accompanying ShotgunFieldManager object
                            used to construct all Shotgun field widgets.
    """
    def __init__(
        self, parent, fields=None, show_labels=True, show_border=False,
        shotgun_field_manager=None, label_exempt_fields=None
    ):
        """
        Constructs a new ListItemWidget.

        :param parant:                  The widget's parent.
        :param fields:                  A list of Shotgun field names to display. Defaults to
                                        ["code", "entity"].
        :param show_labels:             Whether to show labels for fields being
                                        displayed.
        :param shotgun_field_manager:   An optional ShotgunFieldManager object. If
                                        one is not provided one will be instantiated.
        :param label_exempt_fields:     A list of field names that are exempt from having
                                        labels displayed.
        """
        QtGui.QWidget.__init__(self, parent)

        self.ui = Ui_ListItemWidget() 
        self.ui.setupUi(self)

        self.field_manager = shotgun_field_manager or ShotgunFieldManager()
        self.field_manager.initialize()

        self._entity = None
        self._show_border = show_border
        self._fields = OrderedDict()
        self._show_labels = show_labels

        self.fields = fields or ["code", "entity"]

        if label_exempt_fields:
            self.label_exempt_fields = label_exempt_fields

        self.set_selected(False)

    ##########################################################################
    # properties

    def _get_fields(self):
        """
        Returns a list of field names currently registered with the item.
        """
        return self._fields.keys()

    def _set_fields(self, fields):
        """
        Replaces the existing list of fields with those provided. All
        existing fields will be removed from the item, including any
        labels and widgets associated with them. The new list of fields
        will then be added to the item.

        :param fields:  List of Shotgun field names as strings.
        """
        self.clear_fields()

        for field_name in fields:
            self.add_field(field_name)

    fields = property(_get_fields, _set_fields)

    def _get_label_exempt_fields(self):
        """
        Returns a list of field names that are exempt from receiving
        labels in the item's layout.
        """
        return [f for f, d in self._fields.iteritems() if d["label_exempt"]]

    def _set_label_exempt_fields(self, fields):
        """
        Sets which fields are exempt from receiving labels in the item's
        layout. Note that any fields provided here that reference fields
        not currently registered the item will be disregarded. Adding
        those fields to the item after setting label_exempt_fields will
        not automatically cause the newly-added field to inherit the
        label-exempt status.

        :param fields:  A list of Shotgun field names as strings.
        """
        for field_name, field_data in self._fields.iteritems():
            now_exempt = (field_name in fields)

            if self._entity:
                previously_exempt = field_data["label_exempt"]

                # If the state is changing for this field, then we
                # need to rebuild its widgets in the layout.
                if previously_exempt != now_exempt:
                    self.remove_field(field_name)
                    self.add_field(field_name, label_exempt=now_exempt)
            else:
                self._fields[field_name]["label_exempt"] = now_exempt

    label_exempt_fields = property(_get_label_exempt_fields, _set_label_exempt_fields)

    def _get_show_labels(self):
        """
        Whether labels are shown for field widgets displayed by the
        item.
        """
        return self._show_labels

    def _set_show_labels(self, state):
        if bool(state) == self._show_labels:
            return

        self._show_labels = bool(state)

        if not self._entity:
            return

        # Re-add all of the current fields. This will cause the item to
        # clear its fields list and rebuild the layout. Since _show_labels
        # will be False when this happens, we will end up in the correct
        # state.
        self._show_labels = bool(state)
        current_fields = self.fields
        self.fields = current_fields

    show_labels = property(_get_show_labels, _set_show_labels)

    ##########################################################################
    # public methods

    def add_field(self, field_name, label_exempt=False):
        """
        Adds the given field to the list of Shotgun entity fields displayed
        by the widget.

        :param field_name:      The Shotgun entity field name to add.
        :param label_exempt:    Whether to exempt the field from having a label
                                in the item layout. Defaults to False.
        """
        if field_name in self.fields:
            return

        self._fields[field_name] = OrderedDict(
            widget=None,
            label=None,
            label_exempt=label_exempt,
        )

        # If we've not yet loaded an entity, then we don't need to
        # do any widget work.
        if not self._entity:
            return

        field_widget = self.field_manager.create_display_widget(
            self._entity.get("type"),
            field_name,
            self._entity,
        )

        self._fields[field_name]["widget"] = field_widget

        if self.show_labels:
            # If this field is exempt from having a label, then it
            # goes into the layout in column 0, but with the column
            # span set to -1. This will cause it to occupy all of the
            # space on this row of the layout instead of just the first
            # column.
            if field_name in self.label_exempt_fields:
                # If there's no label, then the widget goes in the first
                # column and is set to span all columns.
                self.ui.field_grid_layout.addWidget(field_widget, len(self.fields), 0, 1, -1)
            else:
                # We have a label, so we put that in column 0 and the
                # field widget in column 1.
                field_label = self.field_manager.create_label(
                    self._entity.get("type"),
                    field_name,
                )
                self._fields[field_name]["label"] = field_label
                self.ui.field_grid_layout.addWidget(field_label, len(self.fields), 0)
                self.ui.field_grid_layout.addWidget(field_widget, len(self.fields), 1)
        else:
            # Nothing at all will have labels, so we can just put the
            # widget into column 0. No need to worry about telling it to
            # span any additional columns, because there will only be a
            # single column.
            self.ui.field_grid_layout.addWidget(field_widget, len(self.fields), 0)

    def clear_fields(self):
        """
        Removes all field widgets from the item.
        """
        field_names = self.fields

        for field_name in field_names:
            self.remove_field(field_name)

    def get_visible_fields(self):
        """
        Returns a list of field names that are currently visible.
        """
        # If we have no entity, we have no widgets. If we have no widgets
        # then we definitely don't have anything visible.
        if not self._entity:
            return []

        return [f for f, d in self._fields.iteritems() if d["widget"].isVisible()]

    def remove_field(self, field_name):
        """
        Removes the field widget and its label (when present) for the
        given field name.

        :param field_name:  The Shotgun field name to remove.
        """
        if field_name not in self.fields:
            return

        # Now ditch the widget for the field.
        field_widget = self._fields[field_name]["widget"]

        if not field_widget:
            return

        field_widget.hide()
        self.ui.field_grid_layout.removeWidget(field_widget)

        # If there's a label, then also remove that.
        field_label = self._fields[field_name]["label"]

        if field_label:
            field_label.hide()
            self.ui.field_grid_layout.removeWidget(field_label)

        # Remove the field from the list of stuff we're tracking.
        del self._fields[field_name]

    def set_entity(self, entity):
        """
        Sets the widget's entity and builds or refreshes the thumbnail
        and any fields being displayed.

        :param entity:  The Shotgun entity data dict, as returned from
                        the Shotgun Python API.
        """
        # Don't bother if it's the same entity we already have.
        if self._entity and self._entity == entity:
            return

        # If we've already been populated previously, then we will
        # set the values of the existing field widgets. Otherwise
        # this is a first-time setup and we need to create and place
        # the field widgets into the layout.
        if self._entity:
            self._entity = entity
            self.thumbnail.set_value(entity.get("image"))

            for field, field_data in self._fields.iteritems():
                field_widget = field_data["widget"]

                if field_widget:
                    field_widget.set_value(entity.get(field))
        else:
            self._entity = entity
            self.thumbnail = self.field_manager.create_display_widget(
                entity.get("type"),
                "image",
                self._entity,
            )

            # The stretch factor helps the item widget scale horizontally
            # in a sane manner while generally pushing the field grid
            # layout toward the thumbnail on the left.
            self.ui.box_layout.setStretchFactor(self.ui.right_layout, 15)
            self.ui.box_layout.setStretchFactor(self.ui.left_layout, 7)

            # Setting the size policy for the thumbnail ensures that it
            # doesn't get completely crowded out somehow. It will fill its
            # layout horizontally, taking up a total share of space dictated
            # by the stretch factors above.
            size_policy = QtGui.QSizePolicy(
                QtGui.QSizePolicy.Preferred,
                QtGui.QSizePolicy.MinimumExpanding,
            )

            self.thumbnail.setSizePolicy(size_policy)
            self.ui.left_layout.insertWidget(0, self.thumbnail)

            # Visually, this will just cause column 1 of the grid layout
            # to fill any remaining space to the right of the grid within
            # the parent layout.
            field_grid_layout = self.ui.field_grid_layout
            field_grid_layout.setColumnStretch(1, 3)

            for i, field in enumerate(self.fields):
                field_widget = self.field_manager.create_display_widget(
                    entity.get("type"),
                    field,
                    self._entity,
                )

                # If we've been asked to show labels for the fields, then
                # build those and get them into the layout.
                if self.show_labels:
                    # If this field is exempt from having a label, then it
                    # goes into the layout in column 0, but with the column
                    # span set to -1. This will cause it to occupy all of the
                    # space on this row of the layout instead of just the first
                    # column.
                    if field in self.label_exempt_fields:
                        field_grid_layout.addWidget(field_widget, i, 0, 1, -1)
                    else:
                        field_label = self.field_manager.create_label(
                            entity.get("type"),
                            field,
                        )

                        field_grid_layout.addWidget(field_label, i, 0)
                        self._fields[field]["label"] = field_label
                        field_grid_layout.addWidget(field_widget, i, 1)
                else:
                    field_grid_layout.addWidget(field_widget, i, 0)

                self._fields[field]["widget"] = field_widget

    def set_field_visibility(self, field_name, state):
        """
        Sets the visibility of a field widget by name.

        :param field_name:  The name of the Shotgun field.
        :param state:       True or False
        """
        # If the field isn't registered with the item or if we've
        # not loaded an entity, then there's nothing to do.
        if field_name not in self._fields or not self._entity:
            return

        self._fields[field_name]["widget"].setVisible(bool(state))

        field_label = self._fields[field_name]["label"]

        if field_label:
            field_label.setVisible(bool(state))
                   
    def set_selected(self, selected):
        """
        Adjust the style sheet to indicate selection or not.

        :param selected:    Whether the widget is selected or not.
        """
        p = QtGui.QPalette()
        highlight_col = p.color(QtGui.QPalette.Active, QtGui.QPalette.Highlight)
        highlight_str = "rgb(%s, %s, %s)" % (
            highlight_col.red(),
            highlight_col.green(),
            highlight_col.blue(),
        )
        
        if selected:
            self.ui.box.setStyleSheet(
                """
                #box {
                    border-top-width: 1px;
                    border-bottom-width: 1px;
                    border-right-width: 2px;
                    border-left-width: 2px;
                    border-color: %s;
                    border-style: solid;
                }
                """ % (highlight_str)
            )
        elif self._show_border:
            self.ui.box.setStyleSheet(
                """
                #box {
                    border-top-width: 1px;
                    border-bottom-width: 1px;
                    border-right-width: 2px;
                    border-left-width: 2px;
                    border-color: rgb(66,67,69);
                    border-style: solid;
                }
                """
            )
        else:
            self.ui.box.setStyleSheet("")

    ##########################################################################
    # widget sizing

    def sizeHint(self):
        """
        Tells Qt what the sizeHint for the widget is, based on
        the number of visible field widgets.
        """
        if self._entity:
            fields = self.get_visible_fields()
        else:
            fields = self.fields

        return ListItemWidget.calculate_size(len(fields))

    def minimumSizeHint(self):
        """
        Tells Qt what the minimumSizeHint for the widget is, based on
        the number of visible field widgets.
        """
        return self.sizeHint()

    @staticmethod
    def calculate_size(field_count=2):
        """
        Calculates and returns a suitable size for this widget.

        :param field_count: The integer number of fields to account for
                            when determining the vertical size of the
                            widget. The default assumption is the display
                            of two fields.
        """
        # 0, 1, or 2 fields will all be the same, then we increase
        # as we go above that number of fields.
        height = max((40 + (15 * field_count)), 70)
        return QtCore.QSize(300, height)

