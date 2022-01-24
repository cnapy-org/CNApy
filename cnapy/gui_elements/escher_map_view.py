from pkg_resources import resource_filename
# from time import sleep
import os
from qtpy.QtCore import Slot, QUrl
from qtpy.QtWidgets import QFileDialog
from qtpy.QtWebEngineWidgets import QWebEngineView
import cobra
from cnapy.appdata import AppData

class EscherMapView(QWebEngineView):
    def __init__(self, appdata: AppData, name: str):
        QWebEngineView.__init__(self)
        self.loadFinished.connect(self.handle_load_finished)
        self.load(QUrl.fromLocalFile(resource_filename("cnapy", r"data/escher_new.html")))
        self.page().profile().downloadRequested.connect(self.save_from_escher)
        self.appdata: AppData = appdata
        self.name: str = name # map name for self.appdata.project.maps
        self.editing_enabled = False

    @Slot(bool)
    def handle_load_finished(self, ok: bool):
        if ok:
            # # delay hack needed to wait until DOM is ready 
            # self.page().runJavaScript(r"setTimeout(function(){builder},50)")
            # sleep(0.05)
            self.update()
            self.enable_editing(False)
            self.show()
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
        # only necessary when model was changed
        self.page().runJavaScript("builder.load_model("+cobra.io.to_json(self.appdata.project.cobra_py_model)+")")
        map_data = self.appdata.project.maps[self.name]['escher_map_data']
        if len(map_data) > 0: # probably only necessary when editing is enabled
            self.page().runJavaScript("builder.load_map("+map_data+")")
        if self.appdata.project.comp_values_type == 0:
            self.visualize_fluxes()

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
