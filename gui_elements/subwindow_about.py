#!/usr/bin/env python3
#
# Copyright 2019 PSB & ST
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
""""""

# External modules
import tkinter
import tkinter.scrolledtext


class SubwindowAbout(tkinter.Toplevel):
    """Helper subwindow for showing of license information.

    The window shows copyright information in a label, followed by the
    license text in a textbox.
    """
    def __init__(self, title, info, license_filepath):
        """Constructor of license information subwindow.

        Arguments:
        >title: The subwindow's title.
        >info: The subwindow label's info text.
        >license_filepath: The file path to the shown license.
        """
        super().__init__()
        self.title(title)
        label_info = tkinter.Label(self, text=info)
        label_info.pack()

        if license_filepath is not None:
            with open(license_filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            license_text = ""
            for line in lines:
                license_text += line
                label_license = tkinter.Label(self, text="License:")
            text_license = tkinter.scrolledtext.ScrolledText(self, width=75)
        text_license.insert("end", license_text)
        label_license.pack()
        text_license.pack(fill="both", expand=True)

        self.mainloop()
