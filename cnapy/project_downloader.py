#!/usr/bin/env python3
#
# Copyright 2021 Sven Thiele
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and

import configparser
import os
import pathlib
import shutil
import urllib.request
from configparser import NoOptionError, NoSectionError

import appdirs
import pkg_resources


def main():

    work_directory = os.path.join(
        pathlib.Path.home(), "CNApy-projects")
    conf_path = os.path.join(appdirs.user_config_dir(
        "cnapy", roaming=True, appauthor=False), "cnapy-config.txt")
    config_parser = configparser.RawConfigParser()
    config_parser.read(conf_path)
    try:
        try:
            work_directory = config_parser.get(
                'cnapy-config', 'work_directory')
        except (KeyError, NoOptionError):
            print("Could not find work_directory in cnapy-config.txt")
    except NoSectionError:
        print("Could not find section cnapy-config in cnapy-config.txt")

    if not os.path.exists(work_directory):
        print("Create work directory:", work_directory)
        os.mkdir(work_directory)

        targets = ["ECC2.cna", "ECC2comp.cna", "SmallExample.cna",
                   "iJO1366.cna", "iJOcore.cna", "iML1515.cna", "iMLcore.cna"]
        for t in targets:
            target = os.path.join(work_directory, t)
            if not os.path.exists(target):
                print("Download:", target)
                url = 'https://github.com/cnapy-org/CNApy-projects/releases/download/0.0.3/'+t
                urllib.request.urlretrieve(url, target)

            scen_file = pkg_resources.resource_filename(
                'cnapy', 'data/Ecoli-glucose-standard.scen')
            shutil.copyfile(scen_file, target+"Ecoli-glucose-standard.scen")
            scen_file = pkg_resources.resource_filename(
                'cnapy', 'data/Ecoli-flux-analysis.scen')
            shutil.copyfile(scen_file, target+"Ecoli-flux-analysis.scen")


if __name__ == "__main__":
    main()
