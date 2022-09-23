"""Functions which will be later added to CNAPy's API"""
import requests
from dataclasses import dataclass
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor
from qtpy.QtWidgets import QMessageBox, QTreeWidgetItem


@dataclass()
class IdentifiersOrgResult:
    connection_error: bool
    is_key_valid: bool
    is_key_value_pair_valid: bool


def check_in_identifiers_org(widget: QTreeWidgetItem):
        widget.setCursor(Qt.BusyCursor)
        rows = widget.annotation_widget.annotation.rowCount()
        invalid_red = QColor(255, 0, 0)
        for i in range(0, rows):
            if widget.annotation_widget.annotation.item(i, 0) is not None:
                key = widget.annotation_widget.annotation.item(i, 0).text()
            else:
                key = ""
            if widget.annotation_widget.annotation.item(i, 1) is not None:
                values = widget.annotation_widget.annotation.item(i, 1).text()
            else:
                values = ""
            if (key == "") or (values == ""):
                continue

            if values.startswith("["):
                values = values.replace("', ", "'\b,").replace('", ', '"\b,').replace("[", "")\
                               .replace("]", "").replace("'", "").replace('"', "")
                values = values.split("\b,")
            else:
                values = [values]

            for value in values:
                identifiers_org_result = check_identifiers_org_entry(key, value)

                if identifiers_org_result.connection_error:
                    msgBox = QMessageBox()
                    msgBox.setWindowTitle("Connection error!")
                    msgBox.setTextFormat(Qt.RichText)
                    msgBox.setText("<p>identifiers.org could not be accessed. Either the internet connection isn't working or the server is currently down.</p>")
                    msgBox.setIcon(QMessageBox.Warning)
                    msgBox.exec()
                    break

                if (not identifiers_org_result.is_key_value_pair_valid) and (":" in value):
                    split_value = value.split(":")
                    identifiers_org_result = check_identifiers_org_entry(split_value[0], split_value[1])


                if not identifiers_org_result.is_key_valid:
                    widget.annotation_widget.annotation.item(i, 0).setBackground(invalid_red)

                if not identifiers_org_result.is_key_value_pair_valid:
                    widget.annotation_widget.annotation.item(i, 1).setBackground(invalid_red)

                if not identifiers_org_result.is_key_value_pair_valid:
                    break
        widget.setCursor(Qt.ArrowCursor)


def check_identifiers_org_entry(key: str, value: str) -> IdentifiersOrgResult:
    identifiers_org_result = IdentifiersOrgResult(
        False,
        False,
        False,
    )

    # Check key
    url_key_check = f"https://resolver.api.identifiers.org/{key}"
    try:
        result_object = requests.get(url_key_check)
    except requests.exceptions.RequestException:
        print("HTTP error")
        identifiers_org_result.connection_error = True
        return identifiers_org_result
    result_json = result_object.json()

    if result_json["errorMessage"] is None:
        identifiers_org_result.is_key_valid = True
    else:
        return identifiers_org_result

    # Check key:value pair
    url_key_value_pair_check = f"https://resolver.api.identifiers.org/{key}:{value}"
    try:
        result_object = requests.get(url_key_value_pair_check)
    except requests.exceptions.RequestException:
        print("HTTP error")
        identifiers_org_result.connection_error = True
        return identifiers_org_result
    result_json = result_object.json()

    if result_json["errorMessage"] is None:
        identifiers_org_result.is_key_value_pair_valid = True
    else:
        return identifiers_org_result

    return identifiers_org_result
