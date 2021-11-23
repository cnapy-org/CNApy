"""Functions which will be later added to CNAPy's API"""
import requests
from dataclasses import dataclass
from typing import Tuple


@dataclass()
class IdentifiersOrgResult:
    connection_error: bool
    is_key_valid: bool
    is_key_value_pair_valid :bool


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
