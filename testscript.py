#!/usr/bin/python
import json
import os
from random import randint
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import cobra
from qtpy.QtGui import QColor
from cnapy.cellnetanalyzer import CellNetAnalyzer


def work(cna: CellNetAnalyzer):
    print("Hello")
    open_project(cna, str(os.path.join(
        cna.appdata.work_directory, 'ECC2comp.cna')))
    disco(cna)
    print("I like all colors.")


def disco(cna: CellNetAnalyzer):
    view = cna.centralWidget().map_tabs.widget(0)
    for key in cna.appdata.project.maps["Core Metabolism"]["boxes"]:
        r = randint(1, 255)
        g = randint(1, 255)
        b = randint(1, 255)
        color = QColor(r, g, b)
        view.reaction_boxes[key].set_color(color)
    view = cna.centralWidget().reaction_list
    root = view.reaction_list.invisibleRootItem()
    child_count = root.childCount()
    for i in range(child_count):
        r = randint(1, 255)
        g = randint(1, 255)
        b = randint(1, 255)
        color = QColor(r, g, b)
        item = root.child(i)
        item.setBackground(2, QColor(r, g, b))

    cna.centralWidget().tabs.setCurrentIndex(0)


def open_project(cna, filename):

    temp_dir = TemporaryDirectory()

    with ZipFile(filename, 'r') as zip_ref:
        zip_ref.extractall(temp_dir.name)

        with open(temp_dir.name+"/box_positions.json", 'r') as fp:
            maps = json.load(fp)

            count = 1
            for _name, m in maps.items():
                m["background"] = temp_dir.name + \
                    "/map" + str(count) + ".svg"
                count += 1
        # load meta_data
        with open(temp_dir.name+"/meta.json", 'r') as fp:
            meta_data = json.load(fp)

        cobra_py_model = cobra.io.read_sbml_model(
            temp_dir.name + "/model.sbml")

        cna.appdata.temp_dir = temp_dir
        cna.appdata.project.maps = maps
        cna.appdata.project.meta_data = meta_data
        cna.appdata.project.cobra_py_model = cobra_py_model
        cna.set_current_filename(filename)
        cna.recreate_maps()
        cna.centralWidget().mode_navigator.clear()
        cna.appdata.project.scen_values.clear()
        cna.appdata.scenario_past.clear()
        cna.appdata.scenario_future.clear()
        for r in cna.appdata.project.cobra_py_model.reactions:
            if 'cnapy-default' in r.annotation.keys():
                cna.centralWidget().update_reaction_value(
                    r.id, r.annotation['cnapy-default'])
        cna.nounsaved_changes()

        # if project contains maps move splitter and fit mapview
        if len(cna.appdata.project.maps) > 0:
            (_, r) = cna.centralWidget().splitter2.getRange(1)
            cna.centralWidget().splitter2.moveSplitter(r*0.8, 1)
            cna.centralWidget().fit_mapview()

        cna.centralWidget().update()
