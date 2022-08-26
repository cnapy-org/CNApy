from pkg_resources import resource_filename
from time import sleep
import os
from qtpy.QtCore import Signal, Slot, QUrl, QObject
from qtpy.QtWidgets import QFileDialog
from qtpy.QtWebEngineWidgets import QWebEngineView
from qtpy.QtWebChannel import QWebChannel
import cobra
from cnapy.appdata import AppData
from cnapy.gui_elements.map_view import validate_value
import json

class EscherMapView(QWebEngineView):
    # !!! the associated webwengine process appears not to be properly garbage collected !!!
    # can different pages share the same webengine process? does not appear possible
    # def __init__(self, appdata: AppData, name: str):
    def __init__(self, central_widget, name: str):
        QWebEngineView.__init__(self)
        self.loadFinished.connect(self.handle_load_finished)
        self.loadProgress.connect(self.load_progress)
        # self.resize(1920, 1080) # TODO use actual screen size
        # could resize here to a large size to make the initial escher canvas large
        self.appdata: AppData = central_widget.appdata
        # self.cnapy_bridge = CnapyBridge(self.appdata)
        self.cnapy_bridge = CnapyBridge(self)
        self.channel = QWebChannel()
        self.page().setWebChannel(self.channel)
        self.channel.registerObject("cnapy_bridge", self.cnapy_bridge)
        self.load(QUrl.fromLocalFile(resource_filename("cnapy", r"data/escher_new.html")))
        # sleep(1) # does not help
        # appdata.qapp.processEvents() # does not help
        self.central_widget = central_widget
        self.name: str = name # map name for self.appdata.project.maps
        self.editing_enabled = False

    @Slot(bool)
    # TODO: a call to update() may occur before loading has finished
    def handle_load_finished(self, ok: bool):
        if ok:
            # # delay hack needed to wait until DOM is ready 
            # self.page().runJavaScript(r"setTimeout(function(){builder},50)")
            # sleep(0.05)
            # self.resize(self.sizeHint())
            print("handle_load_finished")
            # self.page().runJavaScript(r"builder = escher.Builder(null, null, null, escher.libs.d3_select('#map_container'), { menu: 'all', fill_screen: true })")
            self.update()
            self.enable_editing(False)
            self.show()
            self.cnapy_bridge.reactionValueChanged.connect(self.central_widget.update_reaction_value)
            self.page().profile().downloadRequested.connect(self.save_from_escher)
            # self.show_geometry_info()
        else:
            raise ValueError("Failed to set up escher_new.html")

    def visualize_fluxes(self):
        self.page().runJavaScript("builder.set_reaction_data(["+
            str({reac_id: flux_val[0] for reac_id, flux_val in self.appdata.project.comp_values.items()})+"])")

    def enable_editing(self, enable: bool):
        self.page().runJavaScript("builder.settings.set('enable_editing', "+str(enable).lower()+")")
        self.editing_enabled = enable

    def update(self):
        print("EscherMapView update")

        # # only necessary when model was changed
        self.page().runJavaScript("builder.load_model("+cobra.io.to_json(self.appdata.project.cobra_py_model)+")")
        map_data = self.appdata.project.maps[self.name].get('escher_map_data', "")
        if len(map_data) > 0: # probably only necessary when editing is enabled
            # here the canvas size in the JSON string could be manipulated before calling load_map
            self.page().runJavaScript("builder.load_map("+map_data+")")

        if self.appdata.project.comp_values_type == 0:
            self.visualize_fluxes()
        # self.show_geometry_info()

    def load_escher_map(self, file_name:str=None):
        if file_name is None:
            file_name: str = QFileDialog.getOpenFileName(
                directory=self.appdata.work_directory, filter="*.json")[0]
            if not file_name or len(file_name) == 0 or not os.path.exists(file_name):
                return

        with open(file_name) as fp:
            self.map_json = json.load(fp)

        self.page().runJavaScript("builder.load_map("+json.dumps(self.map_json)+")")
        self.show_geometry_info()
 
        reaction_bigg_ids = dict()
        for r in self.appdata.project.cobra_py_model.reactions:
            bigg_id = r.annotation.get("bigg.reaction", None)
            if bigg_id is None: # if there is no BiGG ID in the annotation...
                bigg_id = r.id # ... use the reaction ID as proxy
            reaction_bigg_ids[bigg_id] = r.id
    
        offset_x = self.map_json[1]['canvas']['x']
        offset_y = self.map_json[1]['canvas']['y']
        self.appdata.project.maps[self.name]["boxes"] = dict()
        for r in self.map_json[1]["reactions"].values():
            bigg_id = r["bigg_id"]
            if bigg_id in reaction_bigg_ids:
                self.appdata.project.maps[self.name]["boxes"][reaction_bigg_ids[bigg_id]] = [r["label_x"] - offset_x, r["label_y"] - offset_y]

        self.update()

    def show_geometry_info(self):
        print("map (zoomContainer)")
        self.page().runJavaScript("builder.map.get_size()", print)
        print("zoomContainer")
        self.page().runJavaScript("builder.map.zoomContainer.windowTranslate", print)
        self.page().runJavaScript("builder.map.zoomContainer.windowScale", print)
        print("canvas")
        self.page().runJavaScript("builder.map.canvas.sizeAndLocation()", print)

# builder.map.zoomContainer.get_size() -> {width, height} size of the browser display area in pixels, used by zoomBy
# builder.map.canvas: the white background area, its size is not in pixels and not affected by zooming, but its display is affected by zooming 
# after loading escher_new.html: Object { selection: {…}, x: -1495, y: -549, width: 4485, height: 1647, resizeEnabled: true, callbackManager: {…}, mouseNode: {…} }
# canvas size can be changed manually in the browser but not by changing its size attributes; SVG elememts can be placed outside, so what is its purpose?
# initial size comes from zoom_container.get_size() which in turn depends on the initial browser window size:
#   var size = zoomContainer.get_size()
#   canvas_size_and_loc = {
#     x: -size.width,
#     y: -size.height,
#     width: size.width*3,
#     height: size.height*3
# zoomContainer.windowTranslate / windowScale: windowTranslate changes when moving the canvas around
# builder.map.zoomContainer.goTo(1, { x: 0, y: 0 })  0,0 is in upper left (but not the corner), fixed relative to browser window; positive values go down/right
# SVG elements are relative to this origin
# perhaps it is easier to add text boxes on the HTML/javascript level?
    def zoom_by(self, factor: float):
        self.page().runJavaScript(f"builder.zoom_container.zoomBy({factor})")
        self.show_geometry_info()

    def get_scale(self) -> float:
        scale: float = float('nan')
        def set_scale(txt: str):
            nonlocal scale
            scale = float(txt)
            print(txt, scale)
        self.page().runJavaScript("builder.map.zoomContainer.windowScale", set_scale)
        return scale # does not work as expected, perhaps the set_scale callback comes too late?

    # TODO: call this before saving a project
    # also needs to be regularily called (but when?) when the map is editable
    def retrieve_map_data(self):
        def set_escher_map_data(result):
            self.appdata.project.maps[self.name]['escher_map_data'] = result
        self.page().runJavaScript("JSON.stringify(builder.map.map_for_export())", set_escher_map_data)

    @Slot("QWebEngineDownloadItem*") # QWebEngineDownloadItem not declared in qtpy
    def save_from_escher(self, download):
        file_name = os.path.basename(download.path()) # path()/setPath() delared in PyQt
        (_, ext) = os.path.splitext(file_name)
        file_name = QFileDialog.getSaveFileName(directory=self.appdata.work_directory, filter="*"+ext)[0]
        if file_name is None or len(file_name) == 0:
            download.cancel()
        else:
            download.setPath(file_name)
            download.accept()

    def clear_scen_value_txt(self, reac_id: str):
        self.page().runJavaScript('scen_values_txt["'+reac_id+'"] = ""')
    
    def closeEvent(self, event):
        print("Closing Escher map", self.name)
        self.channel.deregisterObject(self.cnapy_bridge)
        super().closeEvent(event)

    @Slot(int)
    def load_progress(self, progress: int):
        print("load_progress", progress)

class CnapyBridge(QObject):
    reactionValueChanged = Signal(str, str)

    def __init__(self, escher_page: EscherMapView): #appdata: AppData):
        QObject.__init__(self)
        self.escher_page: EscherMapView = escher_page
        self.appdata: AppData = self.escher_page.appdata
        # self.appdata: AppData = appdata

    @Slot(str, str)
    def value_changed(self, reaction: str, value: str):
        print(reaction, value)
        if validate_value(value):
            self.reactionValueChanged.emit(reaction, value)

    @Slot(str, result=bool)
    def is_reaction_in_model(self, bigg_id: str) -> bool:
        # in Escher the IDs are called "bigg_id"
        print(bigg_id, type(bigg_id))
        try:
            self.appdata.project.cobra_py_model.reactions.get_by_id(bigg_id)
            print("OK")
            return True
        except:
            return False

    @Slot(str, result=str)
    def get_scenario_value(self, bigg_id: str) -> str:
        print("get_scenario_value", bigg_id, str(self.appdata.project.scen_values.get(bigg_id, " ")[0]))
        return str(self.appdata.project.scen_values.get(bigg_id, " ")[0])

    # @Slot(str)
    # def flux(self, txt: str):
    #     print(txt)

    # @Slot(int, result=int)
    # def getRef(self, x):
    #     print("inside getRef", x)
    #     return x + 5

    # @Slot(int)
    # def printRef(self, ref):
    #     print("inside printRef", ref)
