from math import copysign
from qtpy.QtCore import Qt, Slot, QSignalBlocker
from qtpy.QtWidgets import (QDialog, QGroupBox, QHBoxLayout, QTableWidget, QCheckBox, QMainWindow,
                            QLabel, QLineEdit, QMessageBox, QPushButton, QAbstractItemView,
                            QRadioButton, QVBoxLayout, QTableWidgetItem, QButtonGroup, QStyledItemDelegate)

from cnapy.utils import QComplReceivLineEdit
from cnapy.core import make_scenario_feasible, QPnotSupportedException
from cnapy.gui_elements.central_widget import ModelTabIndex
import cobra

coefficient_format: str = "{:.4g}"

class CoefficientDelegate(QStyledItemDelegate):
    """
    Use this class to format the coefficients in the table. The coefficients can then
    be stored as numbers and so that proper sorting is possible.
    """
    def __init__(self) -> None:
        super().__init__()

    def displayText(self, data, locale) -> str:
        return coefficient_format.format(data)

class FluxFeasibilityDialog(QDialog):
    def __init__(self, main_window: QMainWindow):
        QDialog.__init__(self, parent=main_window)
        self.setWindowTitle("Make scenario feasible")

        self.main_window: QMainWindow = main_window
        self.appdata = main_window.appdata

        self.layout = QVBoxLayout()

        g1 = QGroupBox("Resolve infeasibility minimizing the weighted changes with:")
        s1 = QHBoxLayout()
        self.method_lp = QRadioButton("Linear Program")
        s1.addWidget(self.method_lp)
        self.method_qp = QRadioButton("Quadratic Program")
        s1.addWidget(self.method_qp)
        self.method_lp.setChecked(True)
        g1.setLayout(s1)
        self.layout.addWidget(g1)

        self.flux_group = QGroupBox("Allow corrections to given fluxes using the following weights:")
        self.flux_group.setCheckable(True)
        s2 = QVBoxLayout()
        hbox = QHBoxLayout()
        self.fixed_weight_button = QRadioButton("Weight all fluxes equally")
        hbox.addWidget(self.fixed_weight_button)
        self.abs_flux_weights_button = QRadioButton("Relative to given flux (reciprocal of absolute flux)")
        hbox.addWidget(self.abs_flux_weights_button)
        hbox.addStretch()
        s2.addLayout(hbox)
        l21 = QHBoxLayout()
        self.weights_key_button = QRadioButton("Use reciprocal of value from annotation with key: ")
        l21.addWidget(self.weights_key_button)
        self.weights_key = QLineEdit("variance")
        l21.addWidget(self.weights_key)
        s2.addLayout(l21)
        self.abs_flux_weights_button.setChecked(True)
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Default weight/scale factor: "))
        self.flux_weight_scale = QLineEdit()
        self.flux_weight_scale.setText("1.0")
        h1.addWidget(self.flux_weight_scale)
        h1.addWidget(QLabel("Reciprocal of this is used where a value from the\nannotation is unavailable or to scale the weights."))
        s2.addLayout(h1)
        self.flux_group.setLayout(s2)
        self.layout.addWidget(self.flux_group)

        self.bm_group = QGroupBox("Allow adjustments to the biomass reaction (needs fixed growth rate):")
        self.bm_group.setCheckable(True)
        self.bm_group.toggled.connect(self.bm_group_toggled)
        vbox = QVBoxLayout()
        hbox = QHBoxLayout()
        self.bm_label = QLabel("Biomass reaction: ")
        hbox.addWidget(self.bm_label)
        self.bm_reac_id_select = QComplReceivLineEdit(self, self.appdata.project.cobra_py_model.reactions.list_attr("id"))
        self.bm_reac_id_select.setPlaceholderText("Choose a biomass reaction")
        self.bm_reac_id_select.textCorrect.connect(self.verify_biomass_reaction)
        hbox.addWidget(self.bm_reac_id_select)
        self.bm_mod_scenario = QCheckBox("Add modified biomass reaction to scenario")
        self.bm_mod_scenario.setChecked(True)
        hbox.addWidget(self.bm_mod_scenario)
        vbox.addLayout(hbox)

        self.adjust_bm_coeff = QGroupBox("Select adjustable biomass constituents:")
        self.adjust_bm_coeff.setCheckable(True)
        vbox_bm_coeff = QVBoxLayout()
        self.bm_constituents: QTableWidget = QTableWidget(0, 6)
        self.bm_constituents.setHorizontalHeaderLabels(["   ", "Component", "Formula", "Coefficient", "Adjustment", "Change [%]"])
        self.bm_constituents.setSortingEnabled(True)
        self.bm_constituents.verticalHeader().setVisible(False)
        self.bm_constituents.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.bm_constituents.resizeColumnsToContents()
        coefficient_delegate = CoefficientDelegate()
        self.bm_constituents.setItemDelegateForColumn(3, coefficient_delegate)
        self.bm_constituents.setItemDelegateForColumn(4, coefficient_delegate)
        self.bm_constituents.setItemDelegateForColumn(5, coefficient_delegate)
        vbox_bm_coeff.addWidget(self.bm_constituents)
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("Maximal relative coefficient change [%]:"))
        self.max_coeff_change = QLineEdit("30")
        hbox.addWidget(self.max_coeff_change)
        hbox.addWidget(QLabel("Minimize changes in:"))
        bg = QButtonGroup()
        self.bm_mmol = QRadioButton("mmol")
        self.bm_mmol.setChecked(True)
        bg.addButton(self.bm_mmol)
        hbox.addWidget(self.bm_mmol)
        self.bm_gram = QRadioButton("gram")
        bg.addButton(self.bm_gram)
        hbox.addWidget(self.bm_gram)
        vbox_bm_coeff.addLayout(hbox)
        self.adjust_bm_coeff.setLayout(vbox_bm_coeff)
        vbox.addWidget(self.adjust_bm_coeff)

        self.adjust_gam = QGroupBox("Allow adjustment of growth-associated ATP maintenance (GAM):")
        self.adjust_gam.setCheckable(True)
        vbox_gam = QVBoxLayout()
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("Metabolites in ATP hydrolysis (ATP + H2O -> ADP + Pi + H):"))
        self.gam_mets = QLineEdit("")
        hbox.addWidget(self.gam_mets)
        vbox_gam.addLayout(hbox)
        hbox = QHBoxLayout()
        self.remove_gam_from_bm = QCheckBox("Remove GAM from biomass equation (based on metabolite or fixed amount):")
        self.remove_gam_from_bm.setChecked(False)
        hbox.addWidget(self.remove_gam_from_bm)
        self.remove_gam_via = QLineEdit()
        hbox.addWidget(self.remove_gam_via)
        vbox_gam.addLayout(hbox)
        if "ATPM" in self.appdata.project.cobra_py_model.reactions:
            gam_mets = [met.id for met in self.appdata.project.cobra_py_model.reactions.get_by_id("ATPM").metabolites]
            self.gam_mets.setText(" ".join(gam_mets))
            adp = [met for met in gam_mets if 'adp' in met.lower()]
            if len(adp) == 1:
                self.remove_gam_via.setText(adp[0])
                self.remove_gam_from_bm.setChecked(True)
        else:
            self.adjust_gam.setChecked(False)
            self.gam_mets.setPlaceholderText("atp adp pi h2o h")
            self.remove_gam_via.setPlaceholderText("adp")
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("Maximal change in ATP amount: "))
        self.gam_max_change = QLineEdit("20")
        hbox.addWidget(self.gam_max_change)
        vbox_gam.addLayout(hbox)        
        hbox.addWidget(QLabel("Weight for ATP change: "))
        self.gam_weight = QLineEdit("0.1")
        hbox.addWidget(self.gam_weight)
        vbox_gam.addLayout(hbox)
        self.gam_adjustment = QLabel()
        vbox_gam.addWidget(self.gam_adjustment)
        self.adjust_gam.setLayout(vbox_gam)
        vbox.addWidget(self.adjust_gam)
        self.bm_group.setLayout(vbox)
        self.layout.addWidget(self.bm_group)
        self.enable_biomass_equation_modifications(False)

        self.layout.addWidget(QLabel("Reactions that are set to 0 in the scenario are considered to be switched off."))

        l3 = QHBoxLayout()
        self.button = QPushButton("Compute")
        self.cancel = QPushButton("Close")
        l3.addWidget(self.button)
        l3.addWidget(self.cancel)
        self.layout.addItem(l3)
        self.setLayout(self.layout)

        self.bm_reac_id = ""
        self.bm_mod_reac_id = ""
        self.bm_reac: cobra.Reaction = None
        self.modified_scenario = None

        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)

    @Slot()
    def compute(self):
        abs_flux_weights: bool = False
        weights_key: str = None

        if self.flux_group.isChecked():
            if self.abs_flux_weights_button.isChecked():
                abs_flux_weights = True
            try:
                flux_weight_scale = float(self.flux_weight_scale.text())
            except ValueError:
                flux_weight_scale = 0
            if flux_weight_scale < 0:
                QMessageBox.critical(self, "Invalid default weight",
                    "Default weight must be a positive number.")
                return
            elif self.weights_key_button.isChecked():
                weights_key = self.weights_key.text()
        else:
            flux_weight_scale: float = 0.0

        variable_constituents = []
        max_coeff_change = 0
        gam_mets_param = None
        if self.bm_group.isChecked():
            if not self.growth_rate_fixed():
                self.enable_biomass_equation_modifications(False)
                return
            bm_reac_id = self.bm_reac_id

            if self.adjust_bm_coeff.isChecked():
                for i in range(self.bm_constituents.rowCount()):
                    checkbox = self.bm_constituents.cellWidget(i, 0)
                    if checkbox is not None and checkbox.isChecked():
                        variable_constituents.append(self.bm_constituents.item(i, 1).data(Qt.UserRole))
                    self.bm_constituents.setItem(i, 4, None)
                    self.bm_constituents.setItem(i, 5, None)
                try:
                    max_coeff_change = float(self.max_coeff_change.text())
                except ValueError:
                    max_coeff_change = -1
                if max_coeff_change < 0 or max_coeff_change > 100:
                    QMessageBox.critical(self, "Invalid maximal relative coefficient change",
                        "The maximal relative coefficient change must be a number between 0 and 100.")

                    return
            
            if self.adjust_gam.isChecked():
                gam_mets = self.gam_mets.text().split()
                try:
                    gam_mets = self.appdata.project.cobra_py_model.metabolites.get_by_any(gam_mets)
                except:
                    QMessageBox.critical(self, "Invalid metabolites for ATP hydrolysis",
                            "Check that the metabolites listed for ATP hydrolysis are correct or deactivate GAM adjustment.")
                    return

                if self.remove_gam_from_bm.isChecked():
                    try:
                        gam_base = float(self.remove_gam_via.text())
                    except ValueError:
                        try:
                            gam_base = self.bm_reac.metabolites[
                                self.appdata.project.cobra_py_model.metabolites.get_by_id(self.remove_gam_via.text().strip())]
                        except:
                            QMessageBox.critical(self, "Cannot remove GAM from biomass equation",
                                "Specify either a metabolite of the biomass equation or a number.")
                else:
                    gam_base = 0

                try:
                    gam_max_change = float(self.gam_max_change.text())
                except ValueError:
                    gam_max_change = -1.0
                if gam_max_change < 0:
                    QMessageBox.critical(self, "Invalid maximal ATP change",
                            "The maximal ATP change must be a number greater than 0.")
                    return

                try:
                    gam_weight = float(self.gam_weight.text())
                except ValueError:
                    gam_weight = -1.0
                if gam_weight < 0:
                    QMessageBox.critical(self, "Invalid weight for ATP change",
                            "The weight for ATP change must be a number greater than 0.")
                    return

                gam_mets_param = (gam_mets, gam_max_change, gam_weight, gam_base)
            else:
                gam_mets = []
                gam_mets_param = (gam_mets, 0.0, 0.0, 0.0)
        else:
            bm_reac_id = ""
        
        # if the last scenario change comes from the previous computation undo it
        if self.modified_scenario is self.appdata.scenario_past[-1]:
            self.main_window.undo_scenario_edit()
            self.modified_scenario = None
        if self.bm_mod_reac_id in self.appdata.project.scen_values.reactions:
            del self.appdata.project.scen_values.reactions[self.bm_mod_reac_id]
            self.bm_mod_reac_id = ""
            self.main_window.centralWidget().tabs.widget(ModelTabIndex.Scenario).recreate_scenario_items_needed = True

        self.main_window.setCursor(Qt.BusyCursor)
        try:
            self.appdata.project.solution, reactions_in_objective, bm_mod, gam_mets_sign, gam_adjust = make_scenario_feasible(
                self.appdata.project.cobra_py_model, self.appdata.project.scen_values, use_QP=self.method_qp.isChecked(),
                flux_weight_scale=flux_weight_scale, abs_flux_weights=abs_flux_weights, weights_key=weights_key,
                bm_reac_id=bm_reac_id, variable_constituents=variable_constituents, max_coeff_change=max_coeff_change/100,
                bm_change_in_gram=self.bm_gram.isChecked(), gam_mets_param=gam_mets_param)
            self.main_window.process_fba_solution(update=False)
            if self.appdata.project.solution.status == 'optimal':
                bm_is_modified = len(bm_mod) > 0 or gam_adjust != 0
                if len(reactions_in_objective) > 0:
                    self.main_window.centralWidget().console._append_plain_text(
                        "\nThe fluxes of the following reactions were changed to make the scenario feasible:\n", before_prompt=True)
                    for r in reactions_in_objective:
                        given_value = self.appdata.project.scen_values[r][0]
                        computed_value = self.appdata.project.comp_values[r][0]
                        if abs(given_value - computed_value) > self.appdata.project.cobra_py_model.tolerance:
                            self.main_window.centralWidget().console._append_plain_text(r+": "+self.appdata.format_flux_value(given_value)
                                +" --> "+self.appdata.format_flux_value(computed_value)+"\n", before_prompt=True)
                    scenario_fluxes = [self.appdata.project.comp_values[r] for r in reactions_in_objective]
                    if  bm_is_modified and self.bm_mod_scenario.isChecked():
                        fixed_growth_rate = self.appdata.project.scen_values[bm_reac_id][0]
                        self.appdata.scen_values_set_multiple(reactions_in_objective+[bm_reac_id], scenario_fluxes+[(0, 0)])
                    else:
                        self.appdata.scen_values_set_multiple(reactions_in_objective, scenario_fluxes)
                    self.modified_scenario = self.appdata.scenario_past[-1]
                if bm_is_modified:
                    bm_reac_mod = self.bm_reac.copy()
                    if len(bm_mod) > 0:
                        self.bm_constituents.setSortingEnabled(False)
                        for i in range(self.bm_constituents.rowCount()):
                            met = self.bm_constituents.item(i, 1).data(Qt.UserRole)
                            if met in bm_mod:
                                mod = bm_mod[met]
                                item =  QTableWidgetItem()
                                item.setData(Qt.DisplayRole, mod)
                                self.bm_constituents.setItem(i, 4, item)
                                ref = self.bm_reac.metabolites[met]
                                if met in gam_mets:
                                    ref -= copysign(gam_base, ref)
                                item =  QTableWidgetItem()
                                item.setData(Qt.DisplayRole, 100 * mod/ref)
                                self.bm_constituents.setItem(i, 5, item)
                        self.bm_constituents.setSortingEnabled(True)
                        bm_reac_mod.add_metabolites(bm_mod)
                    bm_reac_mod.add_metabolites({met: sign*gam_adjust for met, sign in zip(gam_mets, gam_mets_sign)})
                    self.main_window.centralWidget().console._append_plain_text("\nModified biomass reaction:\n"
                            +bm_reac_mod.build_reaction_string(), before_prompt=True)
                    if self.bm_mod_scenario.isChecked():
                        self.bm_mod_reac_id = "adjusted_" + bm_reac_id
                        self.appdata.project.scen_values.reactions[self.bm_mod_reac_id] = \
                            [{met.id: coeff for met, coeff in bm_reac_mod.metabolites.items()}, fixed_growth_rate, fixed_growth_rate]
                        self.main_window.centralWidget().tabs.widget(ModelTabIndex.Scenario).recreate_scenario_items_needed = True
                if self.adjust_gam.isChecked():
                    self.gam_adjustment.setText("Calculated GAM adjustment: "+coefficient_format.format(gam_adjust))
                self.main_window.centralWidget().update()
            else:
                QMessageBox.critical(self, "Solver could not find an optimal solution",
                            "No optimal solution was found, solver returned status '"+self.appdata.project.solution.status+"'.")
        except QPnotSupportedException:
            QMessageBox.critical(self, "Solver with support for quadratic objectives required",
                "Choose an appropriate solver, e.g. cplex, gurobi, cbc-coinor (see Configure COBRApy in the Config menu).")
        finally:
            self.main_window.setCursor(Qt.ArrowCursor)

    def update_bm_constituents_table(self):
        self.bm_reac: cobra.Reaction = self.appdata.project.cobra_py_model.reactions.get_by_id(self.bm_reac_id)
        self.bm_constituents.setRowCount(len(self.bm_reac.metabolites))
        self.bm_constituents.setSortingEnabled(False)
        for i, (met, coeff) in enumerate(self.bm_reac.metabolites.items()):
            if met.formula_weight > 0:
                checkbox = QCheckBox()
                self.bm_constituents.setCellWidget(i, 0, checkbox)
                checkbox.setStyleSheet("text-align: center; margin-left:10%; margin-right:10%;")
                checkbox.setChecked(coeff < 0 and met.elements.get('C', 0) > 0
                                    and not met.id.lower().startswith(('datp', 'dgtp', 'dctp', 'dttp')))
            else:
                item = QTableWidgetItem("n/a")
                item.setToolTip("metabolite has no formula")
                self.bm_constituents.setItem(i, 0, item)
            item = QTableWidgetItem(met.id)
            item.setToolTip(met.name)
            item.setData(Qt.UserRole, met)
            self.bm_constituents.setItem(i, 1, item)
            self.bm_constituents.setItem(i, 2, QTableWidgetItem(met.formula))
            item = QTableWidgetItem()
            item.setData(Qt.DisplayRole, coeff)
            self.bm_constituents.setItem(i, 3, item)
        self.bm_constituents.resizeColumnToContents(0)
        self.bm_constituents.setSortingEnabled(True)

    def growth_rate_fixed(self) -> bool:
        if self.bm_reac_id in self.appdata.project.cobra_py_model.reactions:
            scen_val = self.appdata.project.scen_values.get(self.bm_reac_id, None)
            if scen_val is not None and scen_val[0] == scen_val[1]:
                return True
            else:
                QMessageBox.information(self, "Growth rate not fixed in current scenario",
                    "Adjustments to biomass composition are only possible if the growth rate is fixed.")
        else:
            QMessageBox.information(self, "Biomass reaction not set",
                    "Choose a biomass reaction first.")
        return False

    @Slot(bool)
    def verify_biomass_reaction(self, correct: bool) -> bool:
        verified = False
        if correct:
            with QSignalBlocker(self.bm_reac_id_select):
                self.bm_group.setFocus(True) # remove focus from self.bm_reac_id_select to suppress further signals
            self.bm_reac_id = self.bm_reac_id_select.text().strip()
            if self.growth_rate_fixed():
                verified = True
                if self.bm_reac is None or self.bm_reac.id != self.bm_reac_id:
                    self.update_bm_constituents_table()
        self.enable_biomass_equation_modifications(verified)
        return verified

    @Slot(bool)
    def bm_group_toggled(self, on: bool):
        if on:
            self.verify_biomass_reaction(True)
        self.bm_label.setEnabled(True)
        self.bm_reac_id_select.setEnabled(True)

    def enable_biomass_equation_modifications(self, enable: bool):
        self.bm_group.setChecked(enable)
        self.adjust_bm_coeff.setEnabled(enable)
        self.adjust_gam.setEnabled(enable)
