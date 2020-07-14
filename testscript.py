#!/usr/bin/python
from PySide2.QtGui import QColor
from zipfile import ZipFile
from shutil import copyfile
import json
from tempfile import TemporaryDirectory
import time
import cobra
from random import *


def work(cna):
    cna.window.centralWidget().tabs.setCurrentIndex(0)
    time.sleep(.5)
    cna.window.fba()
    time.sleep(.5)
    cna.window.centralWidget().tabs.setCurrentIndex(3)
    time.sleep(.5)
    cna.window.set_onoff()
    cna.window.centralWidget().update()
    time.sleep(.5)
    cna.window.set_heaton()
    cna.window.centralWidget().update()
    time.sleep(1)

    # disco(cna)


def disco(cna):
    print("hello DISCO")
    open_project(cna, 'Disco.cna')

    view = cna.window.centralWidget().tabs.widget(3)
    for i in range(1, 100):
        for key in cna.window.app.appdata.maps[0]["boxes"]:
            r = randint(1, 255)
            g = randint(1, 255)
            b = randint(1, 255)
            color = QColor(r, g, b)
            view.reaction_boxes[key].set_color(color)
            # cna.window.centralWidget().update()

        time.sleep(.05)
        cna.window.centralWidget().update()

    cna.window.centralWidget().tabs.setCurrentIndex(2)
    print("DISCO is over")


def open_project(cna, name):
    folder = TemporaryDirectory()
    with ZipFile(name, 'r') as zip_ref:
        zip_ref.extractall(folder.name)
        with open(folder.name+"/maps.json", 'r') as fp:
            cna.window.app.appdata.maps = json.load(fp)
            for m in cna.window.app.appdata.maps:
                copyfile(folder.name+"/"+m["background"], m["background"])
        cna.window.app.appdata.cobra_py_model = cobra.io.read_sbml_model(
            folder.name + "/model.sbml")
        cna.window.centralWidget().recreate_maps()
