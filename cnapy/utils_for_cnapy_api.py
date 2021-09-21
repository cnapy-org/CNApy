"""Functions which will be later added to CNAPy's API"""
import requests
from typing import Tuple


def check_identifiers_org_entry(key: str, value: str) -> Tuple[bool, bool]:
    url = f"https://resolver.api.identifiers.org/{key}:{value}"
    try:
        result_object = requests.get(url)
    except requests.exceptions.RequestException:
        print("HTTP error")
        return (False, True)
    result_json = result_object.json()

    if result_json["errorMessage"] is None:
        return (True, False)

    return (False, False)
