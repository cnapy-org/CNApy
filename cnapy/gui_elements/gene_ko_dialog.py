"""Dialog for simulating gene knockouts via the Analysis menu."""
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                            QTextEdit, QVBoxLayout)

from cnapy.utils import QComplReceivLineEdit


class GeneKODialog(QDialog):
    """Dialog that accepts a comma-separated list of gene IDs/names,
    evaluates GPR rules, and applies the resulting reaction knockouts
    to the current scenario."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.appdata = main_window.appdata
        self.setWindowTitle("Simulate gene knockouts")
        self.setMinimumWidth(500)

        layout = QVBoxLayout()

        layout.addWidget(QLabel("Enter gene IDs or names (comma-separated):"))

        # Build wordlist: gene IDs + gene names
        model = self.appdata.project.cobra_py_model
        wordlist = sorted(set(
            [g.id for g in model.genes] +
            [g.name for g in model.genes if g.name]
        ))
        self.gene_input = QComplReceivLineEdit(self, wordlist,
                                                check=False, is_constr=False,
                                                reject_empty_string=False)
        self.gene_input.setPlaceholderText("e.g. b0720, adhE, b1241")
        layout.addWidget(self.gene_input)

        btn_layout = QHBoxLayout()
        self.apply_button = QPushButton("Apply to scenario")
        self.apply_button.clicked.connect(self.apply_knockouts)
        btn_layout.addWidget(self.apply_button)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        btn_layout.addWidget(self.close_button)
        layout.addLayout(btn_layout)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(120)
        self.result_text.hide()
        layout.addWidget(self.result_text)

        self.setLayout(layout)

    def apply_knockouts(self):
        from straindesign.networktools import gene_kos_to_constraints

        text = self.gene_input.text().strip()
        if not text:
            self.result_text.setText("No genes specified.")
            self.result_text.show()
            return

        gene_list = [g.strip() for g in text.replace(';', ',').split(',') if g.strip()]
        model = self.appdata.project.cobra_py_model

        # Check for unknown genes
        known_ids = {g.id for g in model.genes}
        known_names = {g.name for g in model.genes if g.name}
        unknown = [g for g in gene_list if g not in known_ids and g not in known_names]

        constraints = gene_kos_to_constraints(model, gene_list)

        if not constraints and not unknown:
            self.result_text.setText(
                f"No reactions affected by knocking out {', '.join(gene_list)}.\n"
                "Other genes can maintain all associated reactions.")
            self.result_text.show()
            return

        # Apply to scenario
        reactions = []
        values = []
        for c in constraints:
            r_id = list(c[0].keys())[0]
            reactions.append(r_id)
            values.append((0.0, 0.0))

        if reactions:
            self.appdata.scen_values_set_multiple(reactions, values)
            self.main_window.centralWidget().update()

        # Report
        lines = []
        if reactions:
            lines.append(f"Knocked out {len(gene_list)} gene(s), "
                        f"{len(reactions)} reaction(s) set to 0:")
            lines.append(', '.join(reactions))
        else:
            lines.append(f"No reactions affected by the specified gene knockouts.")
        if unknown:
            lines.append(f"\nUnknown genes (ignored): {', '.join(unknown)}")
        self.result_text.setText('\n'.join(lines))
        self.result_text.show()

        # Also update genes tab checkboxes to reflect the KOs
        gene_list_widget = self.main_window.centralWidget().gene_list
        gene_list_widget.gene_list.blockSignals(True)
        root = gene_list_widget.gene_list.invisibleRootItem()
        name_to_id = {g.name: g.id for g in model.genes if g.name}
        ko_ids = set()
        for g in gene_list:
            if g in known_ids:
                ko_ids.add(g)
            elif g in name_to_id:
                ko_ids.add(name_to_id[g])
        for i in range(root.childCount()):
            item = root.child(i)
            if item.text(0) in ko_ids:
                item.setCheckState(2, Qt.Unchecked)
        gene_list_widget.gene_list.blockSignals(False)
