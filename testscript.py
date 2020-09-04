#!/usr/bin/python
import json
import time
from random import *
from shutil import copyfile
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import cobra
from PySide2.QtGui import QColor


def work(cna):
    cna.centralWidget().tabs.setCurrentIndex(0)
    time.sleep(.5)
    cna.fba()
    time.sleep(.5)
    cna.centralWidget().tabs.setCurrentIndex(3)
    time.sleep(.5)
    cna.set_onoff()
    cna.centralWidget().update()
    time.sleep(.5)
    cna.set_heaton()
    cna.centralWidget().update()
    time.sleep(1)

    disco(cna)


def disco(cna):
    print("hello DISCO")
    open_project(cna, 'Disco.cna')

    view = cna.centralWidget().tabs.widget(3)
    for i in range(1, 100):
        for key in cna.appdata.project.maps[0]["boxes"]:
            r = randint(1, 255)
            g = randint(1, 255)
            b = randint(1, 255)
            color = QColor(r, g, b)
            view.reaction_boxes[key].set_color(color)
            # cna.centralWidget().update()

        time.sleep(.05)
        cna.centralWidget().update()

    cna.centralWidget().tabs.setCurrentIndex(2)
    print("DISCO is over")


def open_project(cna, name):
    folder = TemporaryDirectory()
    with ZipFile(name, 'r') as zip_ref:
        zip_ref.extractall(folder.name)
        with open(folder.name+"/maps.json", 'r') as fp:
            cna.appdata.project.maps = json.load(fp)
            for m in cna.appdata.project.maps:
                copyfile(folder.name+"/"+m["background"], m["background"])
        cna.appdata.project.cobra_py_model = cobra.io.read_sbml_model(
            folder.name + "/model.sbml")
        cna.centralWidget().recreate_maps()
