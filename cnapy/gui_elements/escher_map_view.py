import importlib.resources as resources
import json
import os
from math import isclose
from typing import Callable
from qtpy.QtCore import Signal, Slot, QUrl, QObject, Qt, QCoreApplication, QEvent
from qtpy.QtWidgets import QFileDialog, QMessageBox
from qtpy.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile, QWebEnginePage
from qtpy.QtWebChannel import QWebChannel
import cobra
from cnapy.appdata import AppData
from cnapy.cobra_cnapy import stoichiometry_hash
from cnapy.gui_elements.map_view import validate_value

class EscherMapView(QWebEngineView):
    web_engine_profile: QWebEngineProfile = None #QWebEngineProfile()
    download_directory: str = ""

    @staticmethod
    @Slot(object) # QWebEngineDownloadItem not declared in qtpy
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
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.initialized = False
        self.central_widget = central_widget
        self.cnapy_bridge = CnapyBridge(self, central_widget)
        self.channel = QWebChannel(self) # reference to channel necessary on Python side for correct operation
        self.page().setWebChannel(self.channel)
        self.channel.registerObject("cnapy_bridge", self.cnapy_bridge)
        html_path = resources.files("cnapy") / "data" / "escher_cnapy.html"
        self.load(QUrl.fromLocalFile(str(html_path)))
        self.name: str = name # map name for self.appdata.project.maps
        self.editing_enabled = False
        self.dark_mode_applied = False
        self.sent_model_hash = None # hash of the model last sent to Escher for editing

    @staticmethod
    def release_web_engine_profile():
        '''deletes the shared profile; all pages using it must already be deleted'''
        profile = EscherMapView.web_engine_profile
        if profile is not None:
            EscherMapView.web_engine_profile = None
            profile.deleteLater()
            QCoreApplication.sendPostedEvents(profile, QEvent.Type.DeferredDelete)

    def finish_setup(self):
        self.page().runJavaScript("setupSearchBar()")
        self.show()
        self.initialized = True
        self.enable_editing(len(self.appdata.project.maps[self.name].get('escher_map_data', "")) == 0)
        self.update()

    def set_cobra_model(self):
        model = self.appdata.project.cobra_py_model
        self.cnapy_bridge.setCobraModel.emit(cobra.io.to_json(model))
        self.sent_model_hash = stoichiometry_hash(model).digest()

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
        if self.central_widget.map_tabs.currentWidget() is self: # otherwise set when switching to this map
            self.central_widget.parent.escher_edit_mode_action.setChecked(enable)

    def update(self):
        if self.initialized:
            if self.appdata.is_in_dark_mode != self.dark_mode_applied:
                self.page().runJavaScript("document.documentElement.style.filter = "+
                    ('"invert(1) hue-rotate(180deg)"' if self.appdata.is_in_dark_mode else '""'))
                self.dark_mode_applied = self.appdata.is_in_dark_mode
            # Escher needs the current model to add reactions from it in edit mode
            if self.editing_enabled and stoichiometry_hash(self.appdata.project.cobra_py_model).digest() != self.sent_model_hash:
                self.set_cobra_model()
            self.visualize_comp_values()

    # currently unused
    # def eventFilter(self, obj: QObject, event: QEvent) -> bool:
    #     print("eventFilter", type(obj), type(event))
    #     return False # keep processing the event

    @Slot()
    def zoom_in(self):
        self.cnapy_bridge.zoomIn.emit()

    @Slot()
    def zoom_out(self):
        self.cnapy_bridge.zoomOut.emit()

    @Slot()
    def zoom_to_canvas(self):
        self.cnapy_bridge.zoomToCanvas.emit()

    def retrieve_map_state(self, done: Callable[[], None]):
        '''Asynchronously copies the map data, position and zoom from Escher into the project map,
        calls done() afterwards. The map data is otherwise only updated in the project when this is called.'''
        if not self.initialized: # the project map still has the data the view was created from
            done()
            return
        mmap = self.appdata.project.maps[self.name] # keep the reference in case the map is renamed or replaced meanwhile
        def set_map_state(result):
            if result is not None: # None if the page could not evaluate the script
                (mmap['escher_map_data'], mmap['pos'], mmap['zoom']) = result
            done()
        self.page().runJavaScript("[JSON.stringify(builder.map.map_for_export()), "+
            "JSON.stringify(builder.map.zoomContainer.windowTranslate), JSON.stringify(builder.map.zoomContainer.windowScale)]",
            set_map_state)

    def focus_reaction(self, reac_id: str):
        # Escher allows the same reaction to be multiple times on a map, so the CNApy search bar is used
        # to highlight all occurrences
        self.central_widget.reaction_searchbar.setText(reac_id)

    def highlight_reaction(self, reac_id: str):
        # highlights and focuses on the first reaction with reac_id
        self.cnapy_bridge.highlightAndFocusReaction.emit(reac_id)

    def jump_to_reaction(self, reac_id: str):
        # highlights and focuses on the next occurrence of reac_id each time it is called
        self.cnapy_bridge.jumpToReaction.emit(reac_id)

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

    def update_selected(self, reaction_ids, metabolite_ids=None, current_reaction_id=None):
        """Highlight the given reaction/metabolite ids (by bigg_id/id) on
        the map. Called from CentralWidget.update_selected with the
        already-resolved id sets for whichever tab/search-bar is active
        (not the raw search text), so that AND-logic / tagged tokens in
        the reaction search bar are already applied before reaching here.

        current_reaction_id, when given (reaction-tab search only), is
        the id of whichever reaction is currently selected in the
        reaction list. On top of the additive orange highlighting of all
        search matches above, that one reaction also gets Escher's
        native single-reaction highlight and the map zooms/pans to it.
        """
        if not reaction_ids and not metabolite_ids:
            # Clear additive CNApy highlights as well as Escher's native
            # search UI; hiding the search bar alone leaves stale matches on
            # the map.
            self.cnapy_bridge.highlightSearchResults.emit([], [])
            self.cnapy_bridge.hideSearchBar.emit()
        else:
            self.cnapy_bridge.highlightSearchResults.emit(list(reaction_ids), list(metabolite_ids or []))
        if current_reaction_id is not None:
            self.highlight_reaction(current_reaction_id)

    def reset_search_highlight(self):
        self.update_selected([], [])

    def search_metabolite(self, search_string: str):
        """Route a metabolite-tab search into Escher's own search bar
        instead of the additive multi-result highlighting used for
        reactions, so the user can use Escher's built-in next/previous
        controls to step through the individual instances of a
        metabolite on the map."""
        if len(search_string) == 0:
            self.cnapy_bridge.hideSearchBar.emit()
        else:
            self.cnapy_bridge.displaySearchBarFor.emit(search_string)

    def dragEnterEvent(self, event):
        event.ignore()


class CnapyBridge(QObject):
    zoomIn = Signal()
    zoomOut = Signal()
    zoomToCanvas = Signal()
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
    jumpToReaction = Signal(str)
    hideSearchBar = Signal()
    displaySearchBarFor = Signal(str)
    highlightSearchResults = Signal('QVariantList', 'QVariantList')  # (reaction bigg_ids, metabolite bigg_ids)
    setCobraModel = Signal(str) # cannot get passing the model dictionary as QVariantMap to work
    enableEditing = Signal(bool)
    visualizeCompValues = Signal('QVariantMap', bool)
    clearReactionData = Signal()

    def __init__(self, escher_map: EscherMapView, central_widget):
        QObject.__init__(self)
        self.escher_map: EscherMapView = escher_map
        self.central_widget = central_widget
        self.appdata: AppData = self.escher_map.appdata
        self.last_accepted_value: str = "" # value of the reaction box input field that was last accepted or set

    def run_on_reaction_box_input(self, statement: str):
        '''statement is executed with input referring to the input field of the reaction tooltip'''
        self.escher_map.page().runJavaScript(
            "(function(input) {if (input) {"+statement+"}})(document.getElementById('reaction-box-input'))")

    def set_input_color(self, valid: bool):
        self.run_on_reaction_box_input("input.style.color = '"+("black" if valid else "red")+"';")

    @Slot(str, str, bool)
    def value_changed(self, reac_id: str, value: str, accept_if_valid: bool):
        if reac_id in self.appdata.project.cobra_py_model.reactions:
            valid = validate_value(value) is not False
            self.set_input_color(valid)
            if valid and accept_if_valid and self.last_accepted_value != value: # avoid redundant calls
                self.last_accepted_value = value
                self.reactionValueChanged.emit(reac_id, value)
                if self.appdata.auto_fba:
                    self.central_widget.parent.fba()
        else:
            valid = value in self.appdata.project.cobra_py_model.reactions
            self.set_input_color(valid)
            if valid and accept_if_valid and self.last_accepted_value != value: # avoid redundant calls
                self.last_accepted_value = value
                ret = QMessageBox.question(self.escher_map, f"Change reaction ID on map to {value}?",
                        "This is only useful if this is the same reaction as in the model but with a different ID on the map because the metabolites displayed on the map will not change!",
                        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                if ret == QMessageBox.StandardButton.Ok:
                    self.escher_map.change_reaction_id(reac_id, value)
                    self.escher_map.update_reaction_stoichiometry(value)
                    self.appdata.window.unsaved_changes()

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
        self.last_accepted_value = ""
        if reac_id in self.appdata.project.scen_values:
            (lb, ub) = self.appdata.project.scen_values[reac_id]
            value = self.appdata.format_flux_value(lb)
            if lb != ub:
                value += ", "+self.appdata.format_flux_value(ub)
            self.last_accepted_value = value
            self.run_on_reaction_box_input("input.value = "+json.dumps(value)+";")
        elif reac_id in self.appdata.project.cobra_py_model.reactions:
            self.run_on_reaction_box_input("input.placeholder = 'enter scenario value'; input.value = '';")
        else:
            self.run_on_reaction_box_input("input.placeholder = 'map to reaction ID...';")

    @Slot(result=list)
    def get_map_and_geometry(self) -> list: # list of strings
        mmap = self.appdata.project.maps[self.escher_map.name]
        return [mmap.get('escher_map_data', ""), mmap["zoom"], mmap["pos"]]

    @Slot(str, str, int)
    def add_map_to_jump_list(self, map_name: str, reac_id: str, count: int):
        reaction_mask = self.central_widget.reaction_list.reaction_mask
        # the reply arrives asynchronously, ignore it if another reaction is shown in the meantime
        if reaction_mask.id.text() == reac_id:
            reaction_mask.jump_list.add(map_name, count)

    @Slot(str, int, int)
    def jump_position_changed(self, reac_id: str, index: int, count: int):
        reaction_mask = self.central_widget.reaction_list.reaction_mask
        if reaction_mask.id.text() == reac_id:
            reaction_mask.jump_list.set_position(self.escher_map.name, index, count)

    @Slot()
    def unsaved_changes(self):
        self.appdata.window.unsaved_changes()
