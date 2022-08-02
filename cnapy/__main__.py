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

import os
import site
from jpype._jvmfinder import getDefaultJVMPath, JVMNotFoundException, JVMNotSupportedException
try:
    getDefaultJVMPath()
except (JVMNotFoundException, JVMNotSupportedException):
    for path in site.getsitepackages():
        # in one of these conda puts the JRE
        os.environ['JAVA_HOME'] = os.path.join(path, 'Library')
        try:
            getDefaultJVMPath()
            break
        except (JVMNotFoundException, JVMNotSupportedException):
            pass

from cnapy.application import Application

def main_cnapy():
    Application()

if __name__ == "__main__":
    main_cnapy()
