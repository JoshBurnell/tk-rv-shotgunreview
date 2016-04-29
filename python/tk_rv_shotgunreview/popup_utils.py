import json
import tank

from tank.platform.qt import QtCore, QtGui

task_manager = tank.platform.import_framework("tk-framework-shotgunutils", "task_manager")
shotgun_model = tank.platform.import_framework("tk-framework-shotgunutils", "shotgun_model")

from .filter_steps_model import FilterStepsModel
from .rel_cuts_model import RelCutsModel
from .rel_shots_model import RelShotsModel
from .filtered_versions_model import FilteredVersionsModel


# XXX not sure how to share this? copied from the mode
required_version_fields = [
    "code",
    "id",
    "entity",
    "sg_first_frame",
    "sg_last_frame",
    "sg_frames_aspect_ratio",
    "sg_frames_have_slate",
    "sg_movie_aspect_ratio",
    "sg_movie_has_slate",
    "sg_path_to_frames",
    "sg_path_to_movie",
    "sg_status_list",
    "sg_uploaded_movie_frame_rate"
    ]


class PopupUtils(QtCore.QObject):

    related_cuts_ready = QtCore.Signal()

    def __init__(self, rv_mode):
        QtCore.QObject.__init__(self)
        self._engine = rv_mode._app.engine
        self._shotgun = rv_mode._bundle.shotgun
        self._project_entity = rv_mode.project_entity
        self._sequence_cuts = []
        self._sequence_entity = None
        self._shot_steps = None
        self._status_schema = None
        self._tray_frame = rv_mode.tray_main_frame
        self._status_menu = None
        self._status_list = []
        self._rv_mode = rv_mode
        self._pipeline_steps_menu = None
        self._pipeline_steps = None
        self._related_cuts_menu = None
        self._last_related_cuts = None
        self._last_rel_shot_entity = None
        self._last_rel_cut_entity = None

        # models

        self._steps_task_manager = task_manager.BackgroundTaskManager(parent=None,
                                                                    start_processing=True,
                                                                    max_threads=2)

        self._steps_model = FilterStepsModel(None, self._steps_task_manager)

        self._rel_cuts_task_manager = task_manager.BackgroundTaskManager(parent=None,
                                                                    start_processing=True,
                                                                    max_threads=2)

        self._rel_cuts_model = RelCutsModel(None, self._rel_cuts_task_manager)

        self._rel_shots_task_manager = task_manager.BackgroundTaskManager(parent=None,
                                                                    start_processing=True,
                                                                    max_threads=2)

        self._rel_shots_model = RelShotsModel(None, self._rel_shots_task_manager)

        
        self._filtered_versions_task_manager = task_manager.BackgroundTaskManager(parent=None,
                                                                    start_processing=True,
                                                                    max_threads=2)

        self._filtered_versions_model = FilteredVersionsModel(None, self._filtered_versions_task_manager)

        # connections
        
        self._rel_cuts_model.data_refreshed.connect(self.on_rel_cuts_refreshed)
        self._rel_shots_model.data_refreshed.connect(self.on_rel_shots_refreshed)
        
        self._steps_model.data_refreshed.connect(self.handle_pipeline_steps_refreshed)
        self.related_cuts_ready.connect(self.create_related_cuts_from_models)

        self._filtered_versions_model.data_refreshed.connect(self.filter_tray)

    # related cuts menu menthods

    def find_rel_cuts_with_model(self, entity_in, shot_entity=None):
        """
        This initiates two queries, one for all related cuts, and the other
        for all related cuts that the shot_entity is in.
        
        XXX we might call this without the shot_entity if we are playing?
        """
        # conditions is an array, with 3 vals
        # [ <field>, 'is', dict ]
        # ['entity', 'is', {'type': 'Sequence', 'id': 31, 'name': '08_a-team'}]
        # ['cut_items.CutItem.shot', 'is', {'type': 'Shot', 'id': 1237}]
        # print "find_rel_cuts_with_model %r %r %r" % (entity_in, shot_entity, self._project_entity['id'])
        self._rel_cuts_done = False
        self._rel_shots_done = False

        conditions = ['entity', 'is', entity_in]
        cut_filters = [ conditions, ['project', 'is', { 'id': self._project_entity['id'], 'type': 'Project' } ]]
        cut_fields = ['id', 'entity', 'code', 'cached_display_name']
        cut_orders = [
            {'field_name': 'code', 'direction': 'asc'}, 
            {'field_name': 'cached_display_name', 'direction': 'asc'}
            ]
        self._rel_cuts_model.load_data(entity_type="Cut", filters=cut_filters, fields=cut_fields, order=cut_orders)        

        if not shot_entity:
            # XXX if there is no shot, then clear the shot model and set the shots done
            self._rel_shots_model.clear()
            self._rel_shots_done = True
            return

        shot_conditions = ['cut_items.CutItem.shot', 'is', { 'id': shot_entity['id'], 'type': 'Shot' }]
        shot_filters = [ shot_conditions, ['project', 'is', { 'id': self._project_entity['id'], 'type': 'Project' } ]]
        shot_fields = ['id', 'entity', 'code', 'cached_display_name']
        shot_orders = [
            {'field_name': 'code', 'direction': 'asc'}, 
            {'field_name': 'cached_display_name', 'direction': 'asc'}
            ]
        self._rel_shots_model.load_data(entity_type="Cut", filters=shot_filters, fields=shot_fields, order=shot_orders)        
        #self._related_timer.start(20)

    def request_related_cuts_from_models(self):
        self._engine.log_info( "request_related_cuts_from_model" )
        
        seq_data = self._rv_mode.sequence_data_from_session()

        if (not seq_data or seq_data["target_entity"]["type"] != "Cut"):
            self._engine.log_info('request_related_cuts_from_models: No cut info available')
            return

        cut_link = seq_data['entity']
        cut_id   = seq_data["target_entity"]["ids"][0]

        version_data = self._rv_mode.version_data_from_source()

        if version_data:
            # mix in second related shots
            version_link = version_data['entity']
            if version_link:
                # version_link might not be a Shot (because version is
                # base-layer, etc)
                if version_link['type'] != "Shot":
                    version_link = None

                # XXX does this allow for cut_link == None ?
                # XXX no it doesnt, what do we do with a cut with no entity link? - sb
                if cut_link != self._last_rel_cut_entity or version_link != self._last_rel_shot_entity:
                    self.find_rel_cuts_with_model(cut_link, version_link)
                    self._last_rel_cut_entity = cut_link
                    self._last_rel_shot_entity = version_link
                    return
                else:
                    # we already have it cached.
                    self.related_cuts_ready.emit()

        # XXX don't get this ? -- alan
        # XXX there was a cut based on a Scene and the query returned the entity we want in a different column - sb.
        if cut_link['type'] == "Scene":
            edit_data = self._rv_mode.edit_data_from_session()
            self.find_rel_cuts_with_model(cut_link, version_link['shot'])
            return

    def handle_related_menu(self, action=None):
        self._engine.log_info("handle_related_menu called with action %r" % action)
        if action.data():
            self._engine.log_info("action.data: %r" % action.data()) 
            self._rv_mode.load_tray_with_something_new({"type":"Cut", "ids":[action.data()['id']]})

    def on_rel_cuts_refreshed(self):
        self._rel_cuts_done = True
        if self._rel_cuts_done and self._rel_shots_done:
            self._rel_shots_done = False
            self._rel_cuts_done = False
            self.related_cuts_ready.emit()

    def on_rel_shots_refreshed(self):
        self._rel_shots_done = True
        if self._rel_cuts_done and self._rel_shots_done:
            self._rel_shots_done = False
            self._rel_cuts_done = False
            self.related_cuts_ready.emit()
        
    def set_project(self, entity):
        # XXX invalidate queries? auto-load status? 
        self._project_entity = entity

    def merge_rel_models_for_menu(self):
        """
        - examine the contents of the shot model and build a map keyed on related shot cut id,
          and an array of related shot cut ids.
        - build an array from the contents of the cuts model,
          and an array of cut ids.
        - if there are ids in the related shots model not present in the related cuts, add them.
        - sort the merged cuts array by the 'cached_display_name' field.
        - examine the sorted array for duplicate 'code' fields. this indicates that several cuts
          are 'revisions' and need to be grouped by this code. add a 'count' column to the dict
          so that the menu creation code can group these together in a sub-menu.
        """
        shot_map = {}
        shot_ids = []

        shot_rows = self._rel_shots_model.rowCount()
        if shot_rows:
            for x in range( 0, shot_rows ):
                item = self._rel_shots_model.index(x, 0)
                sg = shotgun_model.get_sg_data(item)
                shot_ids.append(sg['id'])
                shot_map[sg['id']] = sg
        
        seq_ids = []
        cut_rows = self._rel_cuts_model.rowCount()
        seq_cuts = []
        for x in range(0, cut_rows):
            item = self._rel_cuts_model.index(x, 0)
            sg = shotgun_model.get_sg_data(item)  
            seq_ids.append(sg['id'])
            seq_cuts.append(sg)

        for n in shot_ids:
            if n not in seq_ids:
                seq_cuts.append(shot_map[n])

        sorted_cuts = sorted(seq_cuts, key=lambda x: x['cached_display_name'], reverse=False)
 
        dup_map = {}
        for x in sorted_cuts:
            if x['code'] not in dup_map:
                dup_map[x['code']] = 1
            else:
                dup_map[x['code']] = dup_map[x['code']] + 1
        for x in sorted_cuts:
            x['count'] = dup_map[x['code']]

        return sorted_cuts
 
    def create_related_cuts_from_models(self):
        self._engine.log_info( "create_related_cuts_from_models")
        if not self._related_cuts_menu:
            self._related_cuts_menu = QtGui.QMenu(self._tray_frame.tray_button_browse_cut)
            self._tray_frame.tray_button_browse_cut.setMenu(self._related_cuts_menu)        
            self._related_cuts_menu.aboutToShow.connect(self.request_related_cuts_from_models)
            self._related_cuts_menu.triggered.connect(self.handle_related_menu)

        seq_data = self._rv_mode.sequence_data_from_session()
        cut_id = seq_data["target_entity"]["ids"][0] if seq_data else None
        self._engine.log_info("create_related_cuts_from_models, cut_id: %r" % cut_id)

        seq_cuts = self.merge_rel_models_for_menu()
        if seq_cuts == self._last_related_cuts:
            actions = self._related_cuts_menu.actions()
            for a in actions:
                a.setChecked(False)
                x = a.data()
                if x:
                    if x['id'] == cut_id:
                        a.setChecked(True)

                if a.menu(): # as in a sub-menu
                    a.setChecked(False)
                    sub_acts = a.menu().actions()
                    for b in sub_acts:
                        b.setChecked(False)
                        bd = b.data()
                        if bd['id'] == cut_id:
                            b.setChecked(True)
                            a.setChecked(True)

            return

        self._last_related_cuts = seq_cuts
        self._related_cuts_menu.clear()

        menu = self._related_cuts_menu
        action = QtGui.QAction(self._tray_frame.tray_button_browse_cut)
        action.setText('Related Cuts')
        menu.addAction(action)
        menu.addSeparator()

        last_menu = menu
        parent_menu = None
        last_code = None
        en = {}

        for x in seq_cuts:
            action = QtGui.QAction(self._tray_frame.tray_button_browse_cut)
            action.setCheckable(True)
            action.setChecked(False)
            en['id'] = x['id']
            en['type'] = 'Cut'

            if last_code != x['code']: # this is the first time weve seen this code
                if x['count'] > 1: # make a submenu
                    last_menu = last_menu.addMenu(x['code'])
                    a = last_menu.menuAction()
                    a.setCheckable(True)
                    a.setChecked(False)
                    parent_menu = last_menu
                else:
                    last_menu = menu
                    parent_menu = None
 
            if x['id'] == cut_id:
                action.setChecked(True)
                if parent_menu:
                    a = parent_menu.menuAction()
                    a.setCheckable(True)
                    a.setChecked(True)
            else:
                action.setChecked(False)
 
            action.setText(x['cached_display_name'])
            action.setData(en)
 
            last_menu.addAction(action)
            last_code = x['code']

    # approval status menu methods

    def get_status_list(self, project_entity=None):
        """
        This query needs to be run only when the project changes.
        We cache the last query in memory.
        """
        # XXX - cache all queries in a map for bouncing between projects?
        if not project_entity:
            project_entity = self._project_entity

        if not self._status_schema or project_entity['id'] != self._project_entity['id']:
            self._project_entity = project_entity
            project_id = self._project_entity['id']
            self._status_schema = self._shotgun.schema_field_read('Version', field_name='sg_status_list', project_entity={ 'id': project_id, 'type': 'Project' } )
                
        return self._status_schema

    def get_status_menu(self, project_entity=None):
        """
            status_schema is a large, complicated dictionary of dictionaries.
            this method extracts the bits we are interested in, and builds
            a list of them. 
            below are some examples of interesting things in the schema:
        """
        # print "status_list: %r" % self._status_schema['sg_status_list']
        # print "properties: %r" % self._status_schema['sg_status_list']['properties']
        # print "values: %r" % self._status_schema['sg_status_list']['properties']['valid_values']['value']
        # for x in self._status_schema['sg_status_list']:
            #print "%r" % x
        # print "display values: %r" % self._status_schema['sg_status_list']['properties']['display_values']['value']
        
        s = self.get_status_list(project_entity)
        d = s['sg_status_list']['properties']['display_values']['value']
        status_list = []
        for x in d:
            e = {}
            e[x] = d[x]
            status_list.append(e)
        return status_list

    def build_status_menu(self):
        statii = self.get_status_menu(self._project_entity)
        if not self._status_menu:
            self._status_menu = QtGui.QMenu(self._tray_frame.status_filter_button)
            self._tray_frame.status_filter_button.setMenu(self._status_menu)        
            self._status_menu.triggered.connect(self.handle_status_menu)
        menu = self._status_menu
        menu.clear()
        action = QtGui.QAction(self._tray_frame.status_filter_button)
        action.setCheckable(True)
        action.setChecked(False)
        action.setText('Any Status')
        # XXX what object here?
        action.setData(None)
        menu.addAction(action)
        menu.addSeparator()

        for status in statii:
            action = QtGui.QAction(self._tray_frame.status_filter_button)
            action.setCheckable(True)
            action.setChecked(False)
            for x in status:
                action.setText(status[x])
            action.setData(status)
            menu.addAction(action)

    def handle_status_menu(self, event):
        print "handle_status_menu event: %r" % event.data()
        # if 'any status' is picked, then the other
        # choices are zeroed out. event.data will be None for any status

        self._status_list = []
        actions = self._status_menu.actions()
        if not event.data():
            print 'clearing out status list'
            for a in actions:
                a.setChecked(False)
            self._tray_frame.status_filter_button.setText("Filter by Status")
            return

        name = 'Error'
        count = 0
 
        for a in actions:
            if a.isChecked():
                e = a.data()
                for k in e:
                    self._status_list.append(k)
                    name = e[k]
                    count = count + 1
 
        if count == 0:
            self._tray_frame.status_filter_button.setText("Filter by Status")
        if count == 1:
            self._tray_frame.status_filter_button.setText(name)
        if count > 1:
            self._tray_frame.status_filter_button.setText("%d Statuses" % count)
        
        self.request_versions_for_statuses_and_steps()

    # pipeline steps menu

    def get_pipeline_steps_with_model(self):
        step_filters = [['entity_type', 'is', 'Shot' ]]
        step_fields = ['code', 'list_order', 'short_name', 'id', 'cached_display_name']
        step_orders = [ {'field_name': 'list_order', 'direction': 'desc'} ]
        self._steps_model.load_data(entity_type="Step", filters=step_filters, fields=step_fields, order=step_orders)        

    def handle_pipeline_steps_refreshed(self, refreshed):
        """
        This loads the menu with values returned when the _steps_model returns data_refreshed
        """
        self._engine.log_info('================handle_pipeline_steps_refreshed')

        if not self._pipeline_steps_menu:
            self._pipeline_steps_menu = QtGui.QMenu(self._tray_frame.pipeline_filter_button)
            self._tray_frame.pipeline_filter_button.setMenu(self._pipeline_steps_menu)        
            self._pipeline_steps_menu.triggered.connect(self.handle_pipeline_menu)
        menu = self._pipeline_steps_menu
        menu.clear()

        action = QtGui.QAction(self._tray_frame.pipeline_filter_button)
        action.setCheckable(False)
        action.setChecked(False)
        action.setText('Pipeline Steps Priority')
        # XXX what object do we want here?
        action.setData( None )
        menu.addAction(action)
        menu.addSeparator()

        # XXX latest in pipeline means an empty steps list?
        action = QtGui.QAction(self._tray_frame.pipeline_filter_button)
        action.setCheckable(True)
        action.setChecked(False)
        action.setText('Latest in Pipeline')
        # XXX what object do we want here?
        action.setData( { 'cached_display_name' : 'Latest in Pipeline' } )
        menu.addAction(action)

        rows = self._steps_model.rowCount()

        for x in range(0, rows):
            item = self._steps_model.index(x, 0)
            sg = shotgun_model.get_sg_data(item)
            action = QtGui.QAction(self._tray_frame.pipeline_filter_button)
            action.setCheckable(True)
            action.setChecked(False)
            action.setText(sg['cached_display_name'])
            action.setData(sg)
            menu.addAction(action)

    def handle_pipeline_menu(self, event):
        """
        This is run after the user makes a selection in the Pipeline Steps menu
        """
        # you only get the latest one clicked here. there could be more.
        # you might also get a roll off event that you dont want.
        # so check the widget and then update the button text
        want_latest = False
        if event.data():
            e = event.data()
            if e['cached_display_name'] == 'Latest in Pipeline':
                want_latest = True
        
        actions = self._pipeline_steps_menu.actions()
        count = 0
        name = 'Error'
        # for later filtering, None tells us no step is selected vs [] which means latest in pipeline
        self._pipeline_steps = None
        last_name = None
        for a in actions:
            if a.isChecked():
                count = count + 1
                name = a.data()['cached_display_name']
                # XXX better way?
                if name == 'Latest in Pipeline' and not want_latest:
                    a.setChecked(False)
                    count = count - 1
                    name = last_name
                if a.data()['cached_display_name'] != 'Latest in Pipeline':
                    if self._pipeline_steps == None:
                        self._pipeline_steps = []
                    self._pipeline_steps.append(a.data())
                    if want_latest:
                        a.setChecked(False)
                last_name = name
        if want_latest:
            # an empty list is what the query wants for 'latest in pipeline'
            self._pipeline_steps = []
            name = 'Latest in Pipeline'
            count = 1

        if count == 0:
            self._tray_frame.pipeline_filter_button.setText("Filter by Pipeline")
        if count == 1:
            self._tray_frame.pipeline_filter_button.setText(name)
        if count > 1:
            self._tray_frame.pipeline_filter_button.setText("%d steps" % count)
        self.request_versions_for_statuses_and_steps()

    # methods for 'the crazy query', find versions that match criteria in steps and statuses

    def filters_exist(self):
        if self._status_list or self._pipeline_steps != None:
            return True
        return False

    def filter_tray(self):

        rows = self._filtered_versions_model.rowCount()
        if rows < 1:
            self._engine.log_warning( "Filtering query returned nothing." )
            return None

        shot_map = {}
        for x in range(0, rows):
            item = self._filtered_versions_model.index(x, 0)
            sg = shotgun_model.get_sg_data(item)
            shot_map[sg['entity']['id']] = sg 

        # roll thru the tray and replace
        rows = self._tray_frame.tray_proxyModel.rowCount()
        if rows < 1:
             self._engine.log_warning( "Tray is empty." )
             return None

        for x in range(0,rows):
            item = self._tray_frame.tray_proxyModel.index(x, 0)
            sg = shotgun_model.get_sg_data(item)
            # cut item may not be linked to shot
            if sg['shot'] and sg['shot']['id'] in shot_map:
                v = shot_map[sg['shot']['id']]
                self._tray_frame.tray_delegate.update_rv_role(item, v)
            else:
                self._tray_frame.tray_delegate.update_rv_role(item, None)

        self._tray_frame.tray_model.notify_filter_data_refreshed(True)

    def get_tray_filters(self):
        rows = self._tray_frame.tray_proxyModel.rowCount()
        if rows < 1:
            return []
        shot_list = []
        for x in range(0,rows):
            item = self._tray_frame.tray_proxyModel.index(x, 0)
            sg = shotgun_model.get_sg_data(item)
            if sg['shot']:
                # cut item may not be linked to shot
                shot_list.append(sg['shot'])
        entity_list = [ 'entity', 'in', shot_list ]
        if self._status_list and self._pipeline_steps:
            status_list = ['sg_status_list', 'in', self._status_list ]
            step_list = ['sg_task.Task.step', 'in', self._pipeline_steps]
            filters = [ step_list, status_list, entity_list ]
            return filters
        if self._status_list:
            status_list = ['sg_status_list', 'in', self._status_list ]
            filters = [ status_list, entity_list ]
            return filters
        if self._pipeline_steps:
            step_list = ['sg_task.Task.step', 'in', self._pipeline_steps]
            filters = [ step_list, entity_list ]
            return filters
        return []

    def request_versions_for_statuses_and_steps(self):
        full_filters = self.get_tray_filters()
        version_fields = ["image"] + required_version_fields
        version_filter_presets = [
                {"preset_name": "LATEST", "latest_by": "BY_PIPELINE_STEP_NUMBER_AND_ENTITIES_CREATED_AT" }
            ]

        self._filtered_versions_model.load_data(entity_type='Version', filters=full_filters, 
            fields=version_fields, additional_filter_presets=version_filter_presets)
        