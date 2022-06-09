"""The application data"""
import os
import gurobipy
from configparser import ConfigParser
import pathlib
from tempfile import TemporaryDirectory
from typing import List, Dict, Tuple
from ast import literal_eval as make_tuple
import appdirs
import cobra
from optlang_enumerator.cobra_cnapy import CNApyModel
import pkg_resources
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor
from qtpy.QtWidgets import QMessageBox


class AppData:
    ''' The application data '''

    def __init__(self):
        self.version = "cnapy-1.0.9"
        self.format_version = 1
        self.unsaved = False
        self.project = ProjectData()
        self.modes_coloring = False
        self.scen_color = QColor(255, 0, 127)
        # more scencolors
        self.scen_color_good = QColor(130, 190, 0)
        self.scen_color_warn = QColor(255, 200, 0)
        self.scen_color_bad = Qt.red

        self.box_width = 80
        self.box_height = 40
        self.comp_color = QColor(0, 170, 255)
        self.special_color_1 = QColor(255, 215, 0)
        self.special_color_2 = QColor(150, 220, 0)  # for bounds excluding 0
        self.default_color = QColor(200, 200, 200)
        self.abs_tol = 0.0001
        self.rounding = 3
        self.cna_path = ""
        self.work_directory = str(os.path.join(
            pathlib.Path.home(), "CNApy-projects"))
        self.use_results_cache = False
        self.results_cache_dir: pathlib.Path = pathlib.Path(".")
        self.last_scen_directory = str(os.path.join(
            pathlib.Path.home(), "CNApy-projects"))
        self.temp_dir = TemporaryDirectory()
        self.conf_path = os.path.join(appdirs.user_config_dir(
            "cnapy", roaming=True, appauthor=False), "cnapy-config.txt")
        self.cobrapy_conf_path = os.path.join(appdirs.user_config_dir(
            "cnapy", roaming=True, appauthor=False), "cobrapy-config.txt")
        self.scenario_past = []
        self.scenario_future = []
        self.auto_fba = False

    def scen_values_set(self, reaction: str, values: Tuple[float, float]):
        self.project.scen_values[reaction] = values
        self.scenario_past.append(("set", reaction, values))
        self.scenario_future.clear()

    def scen_values_set_multiple(self, reactions: List[str], values: List[Tuple[float, float]]):
        for r, v in zip(reactions, values):
            self.project.scen_values[r] = v
        self.scenario_past.append(("set", reactions, values))
        self.scenario_future.clear()

    def scen_values_pop(self, reaction: str):
        self.project.scen_values.pop(reaction, None)
        self.scenario_past.append(("pop", reaction, 0))
        self.scenario_future.clear()

    def scen_values_clear(self):
        self.project.scen_values.clear()
        self.scenario_past.append(("clear", "all", 0))
        self.scenario_future.clear()

    def set_comp_value_as_scen_value(self, reaction: str):
        val = self.project.comp_values.get(reaction, None)
        if val:
            self.scen_values_set(reaction, val)

    def recreate_scenario_from_history(self):
        self.project.scen_values = {}
        for (tag, reaction, values) in self.scenario_past:
            if tag == "set":
                if isinstance(reaction, list):
                    for r, v in zip(reaction, values):
                        self.project.scen_values[r] = v
                else:
                    self.project.scen_values[reaction] = values
            elif tag == "pop":
                self.project.scen_values.pop(reaction, None)
            elif tag == "clear":
                self.project.scen_values.clear()

    def format_flux_value(self, flux_value):
        return str(round(float(flux_value), self.rounding)).rstrip("0").rstrip(".")

    def save_cnapy_config(self):
        try:
            fp = open(self.conf_path, "w")
        except FileNotFoundError:
            os.makedirs(appdirs.user_config_dir("cnapy", roaming=True, appauthor=False))
            fp = open(self.conf_path, "w")
        parser = ConfigParser()
        parser.add_section('cnapy-config')
        parser.set('cnapy-config', 'version', self.version)
        parser.set('cnapy-config', 'work_directory', self.work_directory)
        parser.set('cnapy-config', 'scen_color', str(self.scen_color.rgb()))
        parser.set('cnapy-config', 'comp_color', str(self.comp_color.rgb()))
        parser.set('cnapy-config', 'spec1_color', str(self.special_color_1.rgb()))
        parser.set('cnapy-config', 'spec2_color', str(self.special_color_2.rgb()))
        parser.set('cnapy-config', 'default_color', str(self.default_color.rgb()))
        parser.set('cnapy-config', 'box_width', str(self.box_width))
        parser.set('cnapy-config', 'rounding', str(self.rounding))
        parser.set('cnapy-config', 'abs_tol', str(self.abs_tol))
        parser.set('cnapy-config', 'use_results_cache', str(self.use_results_cache))
        parser.set('cnapy-config', 'results_cache_directory', str(self.results_cache_dir))
        parser.write(fp)
        fp.close()

class ProjectData:
    ''' The cnapy project data '''

    def __init__(self):
        self.name = "Unnamed project"
        try:
            self.cobra_py_model = CNApyModel()
        except gurobipy.GurobiError as error:
            msgBox = QMessageBox()
            msgBox.setWindowTitle("Gurobi Error!")
            msgBox.setText("Calculation failed due to the following Gurobi solver error " +\
                        "(if this error cannot be resolved,\ntry using a different solver by changing " +\
                        "it under 'Config->Configure cobrapy'):\n"+error.message+\
                        "\nNOTE: Another error message will follow, you can safely ignore it.")
            msgBox.setIcon(QMessageBox.Warning)
            msgBox.exec()
            return

        default_map = CnaMap("Map")
        self.maps = {"Map": default_map}
        self.scen_values: Dict[str, Tuple[float, float]] = {}
        self.clipboard: Dict[str, Tuple[float, float]] = {}
        self.solution: cobra.Solution = None
        self.comp_values: Dict[str, Tuple[float, float]] = {}
        self.comp_values_type = 0 # 0: simple flux vector, 1: bounds/FVA result
        self.fva_values: Dict[str, Tuple[float, float]] = {} # store FVA results persistently
        self.modes = []
        self.meta_data = {}

    def load_scenario_into_model(self, model):
        for x in self.scen_values:
            try:
                y = model.reactions.get_by_id(x)
            except KeyError:
                print('reaction', x, 'not found!')
            else:
                y.bounds = self.scen_values[x]
                y.set_hash_value()

    def collect_default_scenario_values(self) -> Tuple[List[str], List[Tuple[float, float]]]:
        reactions = []
        values = []
        for r in self.cobra_py_model.reactions:
            if 'cnapy-default' in r.annotation.keys():
                reactions.append(r.id)
                values.append(parse_scenario(r.annotation['cnapy-default']))
        return reactions, values

    # currently unused
    # def scenario_hash_value(self):
    #     return hashlib.md5(pickle.dumps(sorted(self.scen_values.items()))).digest()

def CnaMap(name):
    background_svg = pkg_resources.resource_filename(
        'cnapy', 'data/default-bg.svg')
    return {"name": name,
            "background": background_svg,
            "bg-size": 1,
            "box-size": 1,
            "zoom": 0,
            "pos": (0, 0),
            "boxes": {}
            }

def parse_scenario(text: str) -> Tuple[float, float]:
    """parse a string that describes a valid scenario value"""
    try:
        x = float(text)
        return (x, x)
    except ValueError:
        return(make_tuple(text))
