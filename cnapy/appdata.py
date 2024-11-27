"""The application data"""
import os
import json
import gurobipy
from configparser import ConfigParser
import pathlib
import pkg_resources
from tempfile import TemporaryDirectory
from typing import List, Set, Dict, Tuple
from ast import literal_eval as make_tuple
from math import isclose
import appdirs
from enum import IntEnum

import cobra
from optlang.symbolics import Zero
from optlang_enumerator.cobra_cnapy import CNApyModel
from qtpy.QtCore import Qt, Signal, QObject, QStringListModel
from qtpy.QtGui import QColor, QFont
from qtpy.QtWidgets import QMessageBox

# from straindesign.parse_constr import linexprdict2str # indirectly leads to a JVM restart exception?!?

class ModelItemType(IntEnum):
    Metabolite = 0
    Reaction = 1
    Gene = 2

class AppData(QObject):
    ''' The application data '''

    def __init__(self):
        QObject.__init__(self)
        self.version = "cnapy-1.2.4"
        self.format_version = 2
        self.unsaved = False
        self.project = ProjectData()
        self.modes_coloring = False
        self.scen_color = QColor(255, 0, 127)
        # more scencolors
        self.scen_color_good = QColor(130, 190, 0)
        self.scen_color_warn = QColor(255, 200, 0)
        self.scen_color_bad = Qt.red

        font = QFont()
        font.setFamily(font.defaultFamily())
        self.font_size = font.pointSize()
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
        self.recent_cna_files = []
        self.auto_fba = False

    def scen_values_set(self, reaction: str, values: Tuple[float, float]):
        if self.project.scen_values.get(reaction, None) != values: # record only real changes
            self.project.scen_values[reaction] = values
            self.scenario_past.append(("set", reaction, values))
            self.scenario_future.clear()
            self.unsaved_scenario_changes()

    def scen_values_set_multiple(self, reactions: List[str], values: List[Tuple[float, float]]):
        for r, v in zip(reactions, values):
            self.project.scen_values[r] = v
        self.scenario_past.append(("set", reactions, values))
        self.scenario_future.clear()
        self.unsaved_scenario_changes()

    def scen_values_pop(self, reaction: str):
        self.project.scen_values.pop(reaction, None)
        self.scenario_past.append(("pop", reaction, 0))
        self.scenario_future.clear()
        self.unsaved_scenario_changes()

    def scen_values_clear(self):
        self.project.scen_values.clear_flux_values()
        self.scenario_past.append(("clear", "all", 0))
        self.scenario_future.clear()
        self.unsaved_scenario_changes()

    def set_comp_value_as_scen_value(self, reaction: str):
        val = self.project.comp_values.get(reaction, None)
        if val:
            self.scen_values_set(reaction, val)
        self.unsaved_scenario_changes()

    def recreate_scenario_from_history(self):
        self.project.scen_values.clear_flux_values()
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
                self.project.scen_values.clear_flux_values()
        self.unsaved_scenario_changes()

    def format_flux_value(self, flux_value) -> str:
        return str(round(float(flux_value), self.rounding)).rstrip("0").rstrip(".")

    def flux_value_display(self, vl, vu): #  -> str, color, bool
        # We differentiate special cases like (vl==vu)
        if isclose(vl, vu, abs_tol=self.abs_tol):
            if self.modes_coloring:
                if vl == 0:
                    background_color = Qt.red
                else:
                    background_color = Qt.green
            else:
                background_color = self.comp_color
            as_one = True
            flux_text = self.format_flux_value(vl)
        else:
            if isclose(vl, 0.0, abs_tol=self.abs_tol):
                background_color = self.special_color_1
            elif isclose(vu, 0.0, abs_tol=self.abs_tol):
                background_color = self.special_color_1
            elif vl <= 0 and vu >= 0:
                background_color = self.special_color_1
            else:
                background_color = self.special_color_2
            as_one = False
            flux_text = self.format_flux_value(vl) + ", " + self.format_flux_value(vu)
        return flux_text, background_color, as_one

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
        parser.set('cnapy-config', 'font_size', str(self.font_size))
        parser.set('cnapy-config', 'box_width', str(self.box_width))
        parser.set('cnapy-config', 'rounding', str(self.rounding))
        parser.set('cnapy-config', 'abs_tol', str(self.abs_tol))
        parser.set('cnapy-config', 'use_results_cache', str(self.use_results_cache))
        parser.set('cnapy-config', 'results_cache_directory', str(self.results_cache_dir))
        parser.set('cnapy-config', 'recent_cna_files', str(self.recent_cna_files))
        parser.write(fp)
        fp.close()

    def compute_color_onoff(self, value: Tuple[float, float]):
        (vl, vh) = value
        vl = round(vl, self.rounding)
        vh = round(vh, self.rounding)
        if vl < 0.0:
            return QColor.fromRgb(0, 255, 0)
        elif vh > 0.0:
            return QColor.fromRgb(0, 255, 0)
        else:
            return QColor.fromRgb(255, 0, 0)

    def compute_color_heat(self, value: Tuple[float, float], low, high):
        (vl, vh) = value
        vl = round(vl, self.rounding)
        vh = round(vh, self.rounding)
        mean = my_mean((vl, vh))
        if mean > 0.0:
            if high == 0.0:
                h = 255
            else:
                h = round(mean * 255 / high)
            return QColor.fromRgbF(255-h, 255, 255 - h)
        else:
            if low == 0.0:
                h = 255
            else:
                h = round(mean * 255 / low)
            return QColor.fromRgbF(255, 255 - h, 255 - h)

    def low_and_high(self) -> Tuple[int, int]:
        low = 0
        high = 0
        for value in self.project.scen_values.values():
            mean = my_mean(value)
            if mean < low:
                low = mean
            if mean > high:
                high = mean
        for value in self.project.comp_values.values():
            mean = my_mean(value)
            if mean < low:
                low = mean
            if mean > high:
                high = mean
        return (low, high)

    def unsaved_scenario_changes(self):
        self.project.scen_values.has_unsaved_changes = True
        self.unsavedScenarioChanges.emit()

    unsavedScenarioChanges = Signal()

class Scenario(Dict[str, Tuple[float, float]]):
    empty_constraint = (None, "", "")

    # cannot do this because of the import problem
    # @staticmethod
    # def format_constraint(constraint):
    #     return linexprdict2str(constraint[0])+" "+constraint[1]+" "+str(constraint[2])

    def __init__(self):
        super().__init__() # this dictionary contains the flux values
        self.objective_coefficients: Dict[str, float] = {} # reaction ID, coefficient
        self.objective_direction: str = "max"
        self.use_scenario_objective: bool = False
        self.pinned_reactions: Set[str] = set()
        self.description: str = ""
        self.constraints: List[List(Dict, str, float)] = [] # [reaction_id: coefficient dictionary, type, rhs]
        self.reactions = {} # reaction_id: (coefficient dictionary, lb, ub), can overwrite existing reactions
        self.annotations = [] # List of dicts with: { "id": $reac_id, "key": $key_value, "value": $value_at_key }
        self.file_name: str = ""
        self.has_unsaved_changes = False
        self.version: int = 3

    def save(self, filename: str):
        json_dict = {'fluxes': self, 'pinned_reactions': list(self.pinned_reactions), 'description': self.description,
                    'objective_direction': self.objective_direction, 'objective_coefficients': self.objective_coefficients,
                    'use_scenario_objective': self.use_scenario_objective, 'reactions': self.reactions,
                    'constraints': self.constraints, "annotations": self.annotations, 'version': self.version}
        with open(filename, 'w') as fp:
            json.dump(json_dict, fp)
        self.has_unsaved_changes = False

    def load(self, filename: str, appdata: AppData, merge=False) -> Tuple[List[str], List, List]:
        unknown_ids: List(str)= []
        incompatible_constraints = []
        skipped_scenario_reactions = []
        if not merge:
            self.clear()
        with open(filename, 'r') as fp:
            if filename.endswith('scen'): # CNApy scenario
                self.file_name = filename
                json_dict = json.load(fp)
                if {'fluxes', 'pinned_reactions', 'description', 'objective_direction',
                     'objective_coefficients', 'use_scenario_objective', 'version'}.issubset(json_dict.keys()):
                    flux_values = json_dict['fluxes']
                    for reac_id in json_dict['pinned_reactions']:
                        if reac_id in appdata.project.cobra_py_model.reactions:
                            self.pinned_reactions.add(reac_id)
                        else:
                            unknown_ids.append(reac_id)
                    if not merge:
                        self.description = json_dict['description']
                        self.objective_direction = json_dict['objective_direction']
                        all_reaction_ids = set(appdata.project.cobra_py_model.reactions.list_attr("id"))
                        if json_dict['version'] > 1:
                            self.reactions = json_dict['reactions']
                            for reac_id in self.reactions:
                                if reac_id in all_reaction_ids:
                                    skipped_scenario_reactions.append(reac_id)
                            for reac_id in skipped_scenario_reactions:
                                del self.reactions[reac_id]
                            self.constraints = []
                            all_reaction_ids.update(self.reactions)
                            for constr in json_dict['constraints']:
                                if constr[0] is None:
                                    self.constraints.append(Scenario.empty_constraint)
                                elif set(constr[0].keys()).issubset(all_reaction_ids):
                                    self.constraints.append(constr)
                                else:
                                    incompatible_constraints.append(constr)
                            if json_dict['version'] >= 3:
                                self.annotations = json_dict["annotations"]
                        for reac_id, val in json_dict['objective_coefficients'].items():
                            if reac_id in all_reaction_ids:
                                self.objective_coefficients[reac_id] = val
                            else:
                                unknown_ids.append(reac_id)
                        self.use_scenario_objective = json_dict['use_scenario_objective']
                        self.version = 3
                else:
                    flux_values = json_dict
            elif filename.endswith('val'): # CellNetAnalyzer scenario
                self.file_name = ""
                flux_values = dict()
                for line in fp:
                    line = line.strip()
                    if len(line) > 0 and not line.startswith("##"):
                        try:
                            reac_id, val = line.split()
                            val = float(val)
                            flux_values[reac_id] = (val, val)
                        except Exception:
                            print("Could not parse line ", line)

        reactions = []
        scen_values = []
        for reac_id, val in flux_values.items():
            found_reac_id = False
            if reac_id in appdata.project.cobra_py_model.reactions:
                found_reac_id = True
            elif reac_id.startswith("R_"):
                reac_id = reac_id[2:]
                if reac_id in appdata.project.cobra_py_model.reactions:
                    found_reac_id = True
            if found_reac_id:
                reactions.append(reac_id)
                scen_values.append(val)
            else:
                unknown_ids.append(reac_id)
        appdata.scen_values_set_multiple(reactions, scen_values)

        return unknown_ids, incompatible_constraints, skipped_scenario_reactions

    def add_scenario_reactions_to_model(self, model: cobra.Model):
        if len(self.reactions) > 0:
            scenario_metabolites = set()
            for metabolites,_,_ in self.reactions.values():
                scenario_metabolites.update(metabolites.keys())
            scenario_metabolites = scenario_metabolites.difference(model.metabolites.list_attr("id"))
            model.add_metabolites([cobra.Metabolite(met_id) for met_id in scenario_metabolites])
            for reac_id,(metabolites,lb,ub) in self.reactions.items():
                if reac_id in model.reactions: # overwrite existing reaction
                    reaction = model.reactions.get_by_id(reac_id)
                    reaction.subtract_metabolites(reaction.metabolites, combine=True) # remove current metabolites
                else:
                    reaction = cobra.Reaction(reac_id, lower_bound=lb, upper_bound=ub)
                    model.add_reactions([reaction])
                reaction.add_metabolites(metabolites)
                reaction.set_hash_value()

    def clear_flux_values(self):
        super().clear()

    def clear(self):
        super().clear()
        self.__init__()

class IDList(object):
    """
    provides a list of identifiers (id_list) and a corresponding QStringListModel (ids_model)
    the identifiers can be set with the set_ids method
    the implementation guarantees that id() of the properties id_list and ids_model
    is constant so that they can be used like const references
    """
    def __init__(self):
        self._id_list: list = []
        self._ids_model: QStringListModel = QStringListModel()

    def set_ids(self, *id_lists: List[str]):
        self._id_list.clear()
        for id_list in id_lists:
            self._id_list[len(self._id_list):] = id_list
        self._ids_model.setStringList(self._id_list)

    @property # getter only
    def id_list(self) -> List[str]:
        return self._id_list

    @property # getter only
    def ids_model(self) -> QStringListModel:
        return self._ids_model

    def replace_entry(self, old: str, new: str):
        idx = self._id_list.index(old)
        self._id_list[idx] = new
        self._ids_model.setData(self._ids_model.index(idx), new)

    def __len__(self) -> int:
        return len(self._id_list)

class ProjectData:
    ''' The cnapy project data '''

    def __init__(self):
        self.name = "Unnamed project"

        try:
            cobra.Model(id_or_model="empty", name="empty")
        except gurobipy.GurobiError as error:
            # See https://github.com/cnapy-org/CNApy/issues/490 and
            # https://github.com/opencobra/cobrapy/issues/854
            # When Gurobi (or another external solver) is found by cobrapy
            # but not correctly configured, the model cannot be built :-|
            # Hence, in this exception, we try the model instantiation
            # with GLPK in the hope that it works with this solver :3
            configuration = cobra.Configuration()
            configuration.solver = "glpk"

            msgBox = QMessageBox()
            msgBox.setWindowTitle("Gurobi Error!")
            msgBox.setText(
                "Gurobi could not be set as solver due to the following error:\n" +\
                error.message+"\n"+\
                "If this error cannot be resolved, try using a different solver by changing " +\
                "it under 'Config->Configure cobrapy').\n"+\
                "Right now, GLPK is set as alternative solver instead of Gurobi."
            )
            msgBox.setIcon(QMessageBox.Warning)
            msgBox.exec()

        self.cobra_py_model = CNApyModel()
        self.reaction_ids: IDList = IDList() # reaction IDs of the cobra_py_model and scenario reactions

        default_map = CnaMap("Map")
        self.maps = {"Map": default_map}
        self.scen_values: Scenario = Scenario()
        self.clipboard: Dict[str, Tuple[float, float]] = {}
        self.solution: cobra.Solution = None
        self.comp_values: Dict[str, Tuple[float, float]] = {}
        self.comp_values_type = 0 # 0: simple flux vector, 1: bounds/FVA result
        self.fva_values: Dict[str, Tuple[float, float]] = {} # store FVA results persistently
        self.conc_values: Dict[str, float] = {} # Metabolite concentrations
        self.df_values: Dict[str, float] = {} # Driving forces
        self.modes = []
        self.meta_data = {}

    def load_scenario_into_model(self, model: cobra.Model):
        for x in self.scen_values:
            try:
                y = model.reactions.get_by_id(x)
            except KeyError:
                print('reaction', x, 'not found!')
            else:
                y.bounds = self.scen_values[x]
                y.set_hash_value()

        self.scen_values.add_scenario_reactions_to_model(model)

        if self.scen_values.use_scenario_objective:
            model.objective = model.problem.Objective(
                Zero, direction=self.scen_values.objective_direction)
            for reac_id, coeff in self.scen_values.objective_coefficients.items():
                try:
                    reaction: cobra.Reaction = model.reactions.get_by_id(reac_id)
                except KeyError:
                    print('reaction', reac_id, 'not found!')
                else:
                    model.objective.set_linear_coefficients(
                        {reaction.forward_variable: coeff, reaction.reverse_variable: -coeff})

        for (expression, constraint_type, rhs) in self.scen_values.constraints:
            if constraint_type == '=':
                lb = rhs
                ub = rhs
            elif constraint_type == '<=':
                lb = None
                ub = rhs
            elif constraint_type == '>=':
                lb = rhs
                ub = None
            else:
                print("Skipping constraint of unknown type", constraint_type)
                continue
            try:
                reactions = model.reactions.get_by_any(list(expression))
            except KeyError:
                print("Skipping constraint containing a reaction that is not in the model:", expression)
                continue
            constr = model.problem.Constraint(Zero, lb=lb, ub=ub)
            model.add_cons_vars(constr)
            for (reaction, coeff) in zip(reactions, expression.values()):
                constr.set_linear_coefficients({reaction.forward_variable: coeff, reaction.reverse_variable: -coeff})

        reaction_ids = [reaction.id for reaction in model.reactions]
        for annotation in self.scen_values.annotations:
            if "reaction_id" not in annotation.keys():
                continue
            if annotation["reaction_id"] not in reaction_ids:
                continue
            reaction: cobra.Reaction = model.reactions.get_by_id(annotation["reaction_id"])
            reaction.annotation[annotation["key"]] = annotation["value"]

    def collect_default_scenario_values(self) -> Tuple[List[str], List[Tuple[float, float]]]:
        reactions = []
        values = []
        for r in self.cobra_py_model.reactions:
            if 'cnapy-default' in r.annotation.keys():
                reactions.append(r.id)
                values.append(parse_scenario(r.annotation['cnapy-default']))
        return reactions, values

    def update_reaction_id_lists(self):
        self.reaction_ids.set_ids(self.cobra_py_model.reactions.list_attr("id"), self.scen_values.reactions.keys())

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
            "boxes": {},
            "view": "cnapy", # either "cnapy" or "escher"
            "escher_map_data": "" # JSON string
            }

def parse_scenario(text: str) -> Tuple[float, float]:
    """parse a string that describes a valid scenario value"""
    try:
        x = float(text)
        return (x, x)
    except ValueError:
        return(make_tuple(text))

def my_mean(value):
    if isinstance(value, float):
        return value
    else:
        (vl, vh) = value
        return (vl+vh)/2
