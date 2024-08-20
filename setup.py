#!/usr/bin/env python3
#
# Copyright 2022 CNApy organization
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
# limitations under the License.
# -*- coding: utf-8 -*-
from setuptools import setup

setup(
    name='cnapy',
    description='An integrated environment for metabolic network analysis.',
    long_description=open('README.md', encoding="utf8").read(),
    long_description_content_type="text/asciidoc",
    packages=['cnapy', 'cnapy.gui_elements'],
    package_dir={'cnapy': 'cnapy'},
    package_data={'cnapy': [
        'data/*.svg', 'data/escher_cnapy.html', 'data/escher.min.js']},
    # entry_points={'console_scripts': [
    #     'cnapy = cnapy.__main__:main_cnapy']},
)

# console script on Windows is missing, but can call
# python -m cnapy