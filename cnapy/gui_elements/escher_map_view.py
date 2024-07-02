from pkg_resources import resource_filename
import os
from math import isclose
from qtpy.QtCore import Signal, Slot, QUrl, QObject, Qt
from qtpy.QtWidgets import QFileDialog, QMessageBox
from qtpy.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile, QWebEnginePage
from qtpy.QtWebChannel import QWebChannel
import cobra
from cnapy.appdata import AppData
from cnapy.gui_elements.map_view import validate_value

class EscherMapView(QWebEngineView):
    web_engine_profile: QWebEngineProfile = None #QWebEngineProfile()
    download_directory: str = ""

    @staticmethod
    @Slot("QWebEngineDownloadItem*") # QWebEngineDownloadItem not declared in qtpy
    def save_from_escher(download):
        file_name = os.path.basename(download.path()) # path()/setPath() delared in PyQt
        (_, ext) = os.path.splitext(file_name)
        file_name = QFileDialog.getSaveFileName(directory=EscherMapView.download_directory, filter="*"+ext)[0]
        if file_name is None or len(file_name) == 0:
            download.cancel()
        else:
            if not file_name.endswith(ext):
                file_name += ext
            EscherMapView.download_directory = os.path.dirname(file_name)
            download.setPath(file_name)
            download.accept()

    def __init__(self, central_widget, name: str):
        QWebEngineView.__init__(self)
        self.appdata: AppData = central_widget.appdata
        if EscherMapView.web_engine_profile is None:
            EscherMapView.web_engine_profile = QWebEngineProfile()
            EscherMapView.download_directory = self.appdata.work_directory
            EscherMapView.web_engine_profile.downloadRequested.connect(EscherMapView.save_from_escher)
        page = QWebEnginePage(EscherMapView.web_engine_profile, self)
        self.setPage(page)
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.initialized = False
        self.central_widget = central_widget
        self.cnapy_bridge = CnapyBridge(self, central_widget)
        self.channel = QWebChannel() # reference to channel necessary on Python side for correct operation
        self.page().setWebChannel(self.channel)
        self.channel.registerObject("cnapy_bridge", self.cnapy_bridge)
        self.load(QUrl.fromLocalFile(resource_filename("cnapy", r"data/escher_cnapy.html")))
        self.name: str = name # map name for self.appdata.project.maps
        self.editing_enabled = False

    def finish_setup(self):
        print("finish_setup")
        self.page().runJavaScript(
                r"var search_container=document.getElementsByClassName('search-container')[0];var search_field=document.getElementsByClassName('search-field')[0];search_container.style.display='none';document.getElementsByClassName('search-bar-button')[2].hidden=true")
        self.show()
        self.initialized = True
        self.enable_editing(len(self.appdata.project.maps[self.name].get('escher_map_data', "")) == 0)
        self.update()

    def set_map_data(self) -> bool:
        map_data = self.appdata.project.maps[self.name].get('escher_map_data', "")
        if len(map_data) > 0:
            self.page().runJavaScript("builder.load_map("+map_data+")")
            return True
        else:
            return False

    def set_geometry(self):
        self.page().runJavaScript("builder.map.zoomContainer.goTo("+self.appdata.project.maps[self.name]["zoom"]
        +","+self.appdata.project.maps[self.name]["pos"]+")")

    def set_cobra_model(self):
        self.cnapy_bridge.setCobraModel.emit(cobra.io.to_json(self.appdata.project.cobra_py_model))

    def visualize_comp_values(self):
        if len(self.appdata.project.comp_values) == 0:
            self.cnapy_bridge.clearReactionData.emit()
        else:
            if self.appdata.project.comp_values_type == 0:
                self.cnapy_bridge.visualizeCompValues.emit(
                    {reac_id: val[0] for reac_id, val in self.appdata.project.comp_values.items()}, False)
            else: # FVA result, display flux range as text only
                self.cnapy_bridge.visualizeCompValues.emit({reac_id: self.appdata.format_flux_value(val[0])+
                        ("" if isclose(val[0], val[1], abs_tol=self.appdata.abs_tol) else ", "+self.appdata.format_flux_value(val[1]))
                        for reac_id, val in self.appdata.project.comp_values.items()}, True)

    def enable_editing(self, enable: bool):
        if enable:
            self.set_cobra_model()
        self.cnapy_bridge.enableEditing.emit(enable)
        self.editing_enabled = enable

    def update(self):
        if self.initialized:
            if self.editing_enabled:
                self.set_cobra_model() # TODO: is this still required?
            # currently need to handle the checkbox myself
            self.central_widget.parent.escher_edit_mode_action.setChecked(self.editing_enabled)
            self.visualize_comp_values()

    # currently unused
    # def eventFilter(self, obj: QObject, event: QEvent) -> bool:
    #     print("eventFilter", type(obj), type(event))
    #     return False # keep processung the event

    @Slot()
    def zoom_in(self):
        self.cnapy_bridge.zoomIn.emit()

    @Slot()
    def zoom_out(self):
        self.cnapy_bridge.zoomOut.emit()

    # should this be regularily called when the map is editable?
    def retrieve_map_data(self, semaphore = None): # semaphore is a list with one integer to emulate call by reference
        def set_escher_map_data(new_map_data):
            self.appdata.project.maps[self.name]['escher_map_data'] = new_map_data
            if semaphore is not None:
                semaphore[0] += 1
        self.page().runJavaScript("JSON.stringify(builder.map.map_for_export())", set_escher_map_data) # JSON.stringify not strictly necessary

    def retrieve_pos_and_zoom(self, semaphore = None): # semaphore is a list with one integer to emulate call by reference
        def set_pos(result):
            self.appdata.project.maps[self.name]['pos'] = result
        def set_zoom(result):
            self.appdata.project.maps[self.name]['zoom'] = result
        self.page().runJavaScript("JSON.stringify(builder.map.zoomContainer.windowTranslate)", set_pos) # JSON.stringify not strictly necessary
        self.page().runJavaScript("JSON.stringify(builder.map.zoomContainer.windowScale)", set_zoom) # JSON.stringify not strictly necessary
        if semaphore is not None:
            semaphore[0] += 1

    def focus_reaction(self, reac_id: str):
        # Escher allows the same reaction to be multiple times on a map, so we abuse its search bar here
        self.central_widget.searchbar.setText(reac_id)

    def highlight_reaction(self, reac_id: str):
        # highlights and focuses on the first reatcion with reac_id
        self.cnapy_bridge.highlightAndFocusReaction.emit(reac_id)

    def select_single_reaction(self, reac_id: str):
        # highlight all reactions with this reac_id
        self.cnapy_bridge.highlightReaction.emit(reac_id)

    def change_reaction_id(self, old_reac_id: str, new_reac_id: str):
        self.cnapy_bridge.changeReactionId.emit(old_reac_id, new_reac_id)

    def change_metabolite_id(self, old_met_id: str, new_met_id: str):
        self.cnapy_bridge.changeMetId.emit(old_met_id, new_met_id)

    def delete_reaction(self, reac_id: str):
        self.cnapy_bridge.deleteReaction.emit(reac_id)

    def update_reaction_stoichiometry(self, reac_id: str):
        reaction: cobra.Reaction = self.appdata.project.cobra_py_model.reactions.get_by_id(reac_id)
        self.cnapy_bridge.updateReactionStoichiometry.emit(reac_id,
                {m.id: round(c, 4) for m,c in reaction.metabolites.items()}, reaction.reversibility)

    def update_selected(self, find):
        if len(find) == 0:
            self.cnapy_bridge.hideSearchBar.emit()
        else:
            self.cnapy_bridge.displaySearchBarFor.emit(find)

    def dragEnterEvent(self, event):
        event.ignore()

    def closeEvent(self, event):
        self.channel.deregisterObject(self.cnapy_bridge)
        event.accept()


class CnapyBridge(QObject):
    zoomIn = Signal()
    zoomOut = Signal()
    reactionValueChanged = Signal(str, str)
    switchToReactionMask = Signal(str)
    highlightAndFocusReaction = Signal(str)
    highlightReaction = Signal(str)
    deleteReaction = Signal(str)
    jumpToMetabolite = Signal(str)
    changeReactionId = Signal(str, str)
    changeMetId = Signal(str, str)
    updateReactionStoichiometry = Signal(str, 'QVariantMap', bool) # QVariantMap encapsulates a dict
    addMapToJumpListIfReactionPresent = Signal(str, str)
    hideSearchBar = Signal()
    displaySearchBarFor = Signal(str)
    setCobraModel = Signal(str) # cannot get passing the model dictionary as QVariantMap to work
    enableEditing = Signal(bool)
    visualizeCompValues = Signal('QVariantMap', bool)
    clearReactionData = Signal()

    def __init__(self, escher_map: EscherMapView, central_widget):
        QObject.__init__(self)
        self.escher_map: EscherMapView = escher_map
        self.central_widget = central_widget
        self.appdata: AppData = self.escher_map.appdata
        self.last_accepted_value: str = ""

    @Slot(str, str, bool)
    def value_changed(self, reac_id: str, value: str, accept_if_valid: bool):
        if reac_id in self.appdata.project.cobra_py_model.reactions:
            if validate_value(value):
                self.escher_map.page().runJavaScript('document.getElementById("reaction-box-input").setAttribute("style", "color: black")')
                if accept_if_valid and self.last_accepted_value != value: # avoid redundant calls
                    self.last_accepted_value = value
                    self.reactionValueChanged.emit(reac_id, value)
                    if self.appdata.auto_fba:
                        self.central_widget.parent.fba()
            else:
                self.escher_map.page().runJavaScript('document.getElementById("reaction-box-input").setAttribute("style", "color: red")')
        else:
            if value in self.appdata.project.cobra_py_model.reactions:
                self.escher_map.page().runJavaScript('document.getElementById("reaction-box-input").setAttribute("style", "color: black")')
                if accept_if_valid and self.last_accepted_value != value: # avoid redundant calls
                    self.last_accepted_value = value
                    ret = QMessageBox.question(self.escher_map, f"Change reaction ID on map to {value}?",
                            "This is only useful if this is the same reaction as in the model but with a different ID on the map because the metabolites displayed on the map will not change!",
                            QMessageBox.Ok | QMessageBox.Cancel)
                    if ret == QMessageBox.Ok:
                        self.escher_map.change_reaction_id(reac_id, value)
                        self.escher_map.update_reaction_stoichiometry(value)
                        self.central_widget.unsaved_changes()
            else:
                self.escher_map.page().runJavaScript('document.getElementById("reaction-box-input").setAttribute("style", "color: red")')


    @Slot(str, str)
    def clicked_on_id(self, id_type: str, identifier: str):
        if id_type == "reaction" and identifier in self.appdata.project.cobra_py_model.reactions:
            self.switchToReactionMask.emit(identifier)
        elif id_type == "metabolite" and identifier in self.appdata.project.cobra_py_model.metabolites:
            self.jumpToMetabolite.emit(identifier)

    @Slot()
    def finish_setup(self):
        self.escher_map.finish_setup()

    @Slot(str)
    def set_reaction_box_scenario_value(self, reac_id: str):
        if reac_id in self.appdata.project.scen_values:
            (lb, ub) = self.appdata.project.scen_values[reac_id]
            attr_val = "value='"+self.appdata.format_flux_value(lb)
            if lb != ub:
                attr_val += ", "+self.appdata.format_flux_value(ub)
            attr_val += "'"
            self.last_accepted_value = attr_val
        else:
            if reac_id in self.appdata.project.cobra_py_model.reactions:
                self.escher_map.page().runJavaScript(
                    "document.getElementById('reaction-box-input').placeholder='enter scenario value'")
                attr_val = "value=''" # to clear the input field
                self.last_accepted_value = attr_val
            else:
                attr_val = "placeholder='map to reaction ID...'"
        self.escher_map.page().runJavaScript("document.getElementById('reaction-box-input')."+attr_val)

    @Slot(result=list)
    def get_map_and_geometry(self) -> list: # list of strings
        return [self.appdata.project.maps[self.escher_map.name].get('escher_map_data', ""),
                self.appdata.project.maps[self.escher_map.name]["zoom"], self.appdata.project.maps[self.escher_map.name]["pos"]]

    @Slot(str)
    def add_map_to_jump_list(self, map_name: str):
        self.central_widget.reaction_list.reaction_mask.jump_list.add(map_name)

    @Slot()
    def unsaved_changes(self):
        self.appdata.window.unsaved_changes()
