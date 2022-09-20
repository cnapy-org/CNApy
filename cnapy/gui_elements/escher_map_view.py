from pkg_resources import resource_filename
import os
from math import isclose
from qtpy.QtCore import Signal, Slot, QUrl, QObject, Qt
from qtpy.QtWidgets import QFileDialog
from qtpy.QtWebEngineWidgets import QWebEngineView
from qtpy.QtWebChannel import QWebChannel
import cobra
from cnapy.appdata import AppData
from cnapy.gui_elements.map_view import validate_value

class EscherMapView(QWebEngineView):
    def __init__(self, central_widget, name: str):
        QWebEngineView.__init__(self)
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.initialized = False
        self.appdata: AppData = central_widget.appdata
        self.central_widget = central_widget
        self.cnapy_bridge = CnapyBridge(self, central_widget)
        self.channel = QWebChannel()
        self.page().setWebChannel(self.channel)
        self.channel.registerObject("cnapy_bridge", self.cnapy_bridge)
        self.load(QUrl.fromLocalFile(resource_filename("cnapy", r"data/escher_cnapy.html")))
        self.name: str = name # map name for self.appdata.project.maps
        self.editing_enabled = False

    @Slot()
    def initial_setup(self):
        self.enable_editing(not self.set_map_data())
        self.set_geometry()
        self.show()
        self.initialized = True
        # set up the Escher search bar, its visibilty will be controlled by CNApy
        self.page().runJavaScript(r"builder.passPropsSearchBar({display:true})",
            lambda x: self.page().runJavaScript(
                r"var search_container=document.getElementsByClassName('search-container')[0];var search_field=document.getElementsByClassName('search-field')[0];search_container.style.display='none';document.getElementsByClassName('search-bar-button')[2].hidden=true"))
        self.update()
        self.set_file_selector_download()
        # self.focusProxy().installEventFilter(self) # can be used for event tracking

    def finish_setup(self):
        print("finish_setup")
        self.page().runJavaScript(
                r"var search_container=document.getElementsByClassName('search-container')[0];var search_field=document.getElementsByClassName('search-field')[0];search_container.style.display='none';document.getElementsByClassName('search-bar-button')[2].hidden=true")
        self.show()
        self.initialized = True
        self.enable_editing(len(self.appdata.project.maps[self.name].get('escher_map_data', "")) == 0)
        self.update()
        self.set_file_selector_download()

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
        self.page().runJavaScript("builder.load_model("+cobra.io.to_json(self.appdata.project.cobra_py_model)+")")

    def visualize_comp_values(self):
        js_stack = []
        def set_reaction_data_string(reaction_data):
            return "builder.set_reaction_data("+reaction_data+")"
        if len(self.appdata.project.comp_values) == 0:
            js_stack.append(set_reaction_data_string("null"))
        else:
            if self.appdata.project.comp_values_type == 0:
                 js_stack.append(set_reaction_data_string("["+str({reac_id: val[0]
                                         for reac_id, val in self.appdata.project.comp_values.items()})+"]"))
            else: # FVA result, display flux range as text only
                js_stack.append("let style=builder.map.settings.get('reaction_styles')")
                js_stack.append("builder.map.settings.set('reaction_styles','text')")
                js_stack.append(set_reaction_data_string("["+str({reac_id: self.appdata.format_flux_value(val[0])+
                                        ("" if isclose(val[0], val[1], abs_tol=self.appdata.abs_tol) else ", "+self.appdata.format_flux_value(val[1]))
                                         for reac_id, val in self.appdata.project.comp_values.items()})+"]"))
                js_stack.append("builder.settings._options.reaction_styles=style")
        self.page().runJavaScript("{"+";".join(js_stack)+"}")

    def enable_editing(self, enable: bool):
        enable_str = str(enable).lower()
        not_enable_str = str(not enable).lower()
        if enable:
            tooltip = "[]"
            menu = "block"
            self.set_cobra_model()
        else:
            tooltip = "['object','label']"
            menu = "none"
        self.page().runJavaScript("builder.settings.set('enable_editing',"+enable_str+
            ");builder.settings.set('enable_keys',"+enable_str+ 
            ");builder.settings.set('enable_tooltips',"+tooltip+
            ");document.getElementsByClassName('button-panel')[0].hidden="+not_enable_str+
            ";document.getElementsByClassName('menu-bar')[0].style['display']='"+menu+"'")
        self.editing_enabled = enable

    def update(self):
        if self.initialized:
            if self.editing_enabled:
                self.set_cobra_model()
            # currently need to handle the checkbox myself
            self.central_widget.parent.escher_edit_mode_action.setChecked(self.editing_enabled)
            self.visualize_comp_values()

    # currently unused
    # def eventFilter(self, obj: QObject, event: QEvent) -> bool:
    #     print("eventFilter", type(obj), type(event))
    #     return False # keep processung the event

    @Slot()
    def zoom_in(self):
        self.page().runJavaScript("builder.zoom_container.zoom_in()")

    @Slot()
    def zoom_out(self):
        self.page().runJavaScript("builder.zoom_container.zoom_out()")

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

    def set_file_selector_download(self):
        self.page().profile().downloadRequested.connect(self.save_from_escher)

    @Slot("QWebEngineDownloadItem*") # QWebEngineDownloadItem not declared in qtpy
    def save_from_escher(self, download):
        file_name = os.path.basename(download.path()) # path()/setPath() delared in PyQt
        (_, ext) = os.path.splitext(file_name)
        file_name = QFileDialog.getSaveFileName(directory=self.appdata.work_directory, filter="*"+ext)[0]
        if file_name is None or len(file_name) == 0:
            download.cancel()
        else:
            if not file_name.endswith(ext):
                file_name += ext
            download.setPath(file_name)
            download.accept()

    def focus_reaction(self, reac_id: str):
        # Escher allows the same reaction to be multiple times on a map, so we abuse its search bar here
        self.central_widget.searchbar.setText(reac_id)

    def highlight_reaction(self, reac_id: str):
        # highlights and focuses on the first reatcion with reac_id
        self.page().runJavaScript("highlightAndFocusReaction('"+reac_id+"')")

    def update_selected(self, find: str):
        if len(find) == 0:
            self.page().runJavaScript("search_container.style.display='none'")
        else:
            self.page().runJavaScript("search_container.style.display='';search_field.value='"+find+
                                      "';search_field.dispatchEvent(new Event('input'))")
    
    def dragEnterEvent(self, event):
        event.ignore()

    def closeEvent(self, event):
        self.channel.deregisterObject(self.cnapy_bridge)
        super().closeEvent(event)


class CnapyBridge(QObject):
    reactionValueChanged = Signal(str, str)
    switchToReactionMask = Signal(str)
    jumpToMetabolite = Signal(str)

    def __init__(self, escher_map: EscherMapView, central_widget):
        QObject.__init__(self)
        self.escher_map: EscherMapView = escher_map
        self.central_widget = central_widget
        self.appdata: AppData = self.escher_map.appdata
        self.last_accepted_value: str = ""

    @Slot(str, str, bool)
    def value_changed(self, reac_id: str, value: str, accept_if_valid: bool):
        if validate_value(value):
            self.escher_map.page().runJavaScript('document.getElementById("reaction-box-input").setAttribute("style", "color: black")')
            if accept_if_valid and self.last_accepted_value != value: # avoid redundant calls
                self.last_accepted_value = value
                self.reactionValueChanged.emit(reac_id, value)
                if self.appdata.auto_fba:
                    self.central_widget.parent.fba()
        else:
            self.escher_map.page().runJavaScript('document.getElementById("reaction-box-input").setAttribute("style", "color: red")')

    @Slot(str, str)
    def clicked_on_id(self, id_type: str, identifier: str):
        # needed because the Javascript side apparently cannot emit signals
        if id_type == "reaction" and identifier in self.appdata.project.cobra_py_model.reactions:
            self.switchToReactionMask.emit(identifier)
        elif id_type == "metabolite" and identifier in self.appdata.project.cobra_py_model.metabolites:
            self.jumpToMetabolite.emit(identifier)

    @Slot()
    def begin_setup(self):
        self.escher_map.initial_setup()

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
                attr_val = "value=''" # to clear the input field
                self.last_accepted_value = attr_val
            else:
                attr_val = "remove()" # hidden=true or remove()?
        self.escher_map.page().runJavaScript("document.getElementById('reaction-box-input')."+attr_val)

    @Slot(result=list)
    def get_map_and_geometry(self) -> list: # list of strings
        return [self.appdata.project.maps[self.escher_map.name].get('escher_map_data', ""),
                self.appdata.project.maps[self.escher_map.name]["zoom"], self.appdata.project.maps[self.escher_map.name]["pos"]]
