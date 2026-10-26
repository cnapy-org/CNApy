"""Tests for writing and opening CNApy projects (.cna ZIP files) via the real
MainWindow.write_project_file/save_model/open_project, called unbound on the fake_main_window
from conftest.py, and for SBML/JSON model export round trips.

run: pytest cnapy/tests/test_project_files.py
"""
import json
import types
from zipfile import ZipFile

import cobra
import pytest

from cnapy.appdata import CnaMap, MAP_VIEW_ESCHER
from cnapy.cobra_cnapy import CNApyModel, stoichiometry_hash

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
ESCHER_MAP_DATA = json.dumps([{"map_name": "test"}, {"reactions": {}, "nodes": {}}])


def model_hash(model):
    # independent of the reaction order, which SBML/JSON need not preserve
    return sorted((r.id, r.lower_bound, r.upper_bound,
                   sorted((m.id, float(c)) for m, c in r.metabolites.items()))
                  for r in model.reactions)


@pytest.fixture
def window(fake_main_window, mainwindow_cls, monkeypatch):
    fake = fake_main_window
    for name in ("write_project_file", "save_model", "open_project"):
        setattr(fake, name, types.MethodType(getattr(mainwindow_cls, name), fake))
    fake.centralWidget().splitter2.getRange.return_value = (0, 1000)
    fake.messages = []
    for kind in ("critical", "warning"):
        monkeypatch.setattr("cnapy.gui_elements.main_window.QMessageBox." + kind,
                            lambda *args, kind=kind: fake.messages.append((kind,) + args[1:]))
    return fake


@pytest.fixture
def project_with_maps(window, tmp_path):
    project = window.appdata.project
    svg_path = tmp_path / "background.svg"
    svg_path.write_text(SVG)
    cna_map = CnaMap("CNApy map")
    cna_map["background"] = str(svg_path)
    cna_map["boxes"] = {"EX_glc_e": [10.0, 20.0, False, True], "PGI": [30.0, 40.0, True, False]}
    cna_map["zoom"] = 2
    escher_map = CnaMap("Escher map")
    escher_map["view"] = MAP_VIEW_ESCHER
    escher_map["escher_map_data"] = ESCHER_MAP_DATA
    project.maps = {"CNApy map": cna_map, "Escher map": escher_map}
    project.meta_data = {"description": "test project"}
    project.name = str(tmp_path / "project.cna")
    return project


@pytest.mark.parametrize("as_json", [False, True], ids=["sbml", "json"])
def test_project_round_trip(window, project_with_maps, as_json):
    window.appdata.save_model_as_json = as_json
    project = project_with_maps
    original_hash = model_hash(project.cobra_py_model)
    filename = project.name

    assert window.write_project_file() is True
    with ZipFile(filename) as zip_ref:
        names = set(zip_ref.namelist())
        boxes = json.loads(zip_ref.read("box_positions.json"))
        meta = json.loads(zip_ref.read("meta.json"))
        svg = zip_ref.read("map1.svg").decode()
    assert names == {"model.json" if as_json else "model.sbml", "box_positions.json", "meta.json", "map1.svg"}
    assert boxes["CNApy map"]["background"] == "map1.svg"  # archive name, not the local path
    assert meta == {"description": "test project", "format version": window.appdata.format_version}
    assert svg == SVG
    window.nounsaved_changes.assert_called_once()

    # replace the project, then open the file again
    project.reset()
    window.open_project(filename)
    assert window.messages == []
    window.reset_gui_for_new_project.assert_called_once()
    window.set_current_filename.assert_called_once_with(filename)
    assert model_hash(project.cobra_py_model) == original_hash
    assert isinstance(project.cobra_py_model, CNApyModel)
    assert project.meta_data["description"] == "test project"
    maps = project.maps
    assert list(maps) == ["CNApy map", "Escher map"]
    assert maps["CNApy map"]["boxes"] == {"EX_glc_e": [10.0, 20.0, False, True], "PGI": [30.0, 40.0, True, False]}
    assert maps["CNApy map"]["zoom"] == 2
    with open(maps["CNApy map"]["background"]) as fp:  # extracted into a temporary directory
        assert fp.read() == SVG
    assert maps["Escher map"]["view"] == MAP_VIEW_ESCHER
    assert maps["Escher map"]["escher_map_data"] == ESCHER_MAP_DATA


def test_failed_save_keeps_existing_project_file(window, project_with_maps, tmp_path):
    filename = project_with_maps.name
    assert window.write_project_file() is True
    with open(filename, "rb") as fp:
        saved = fp.read()
    project_with_maps.maps["CNApy map"]["background"] = str(tmp_path / "missing.svg")
    with pytest.raises(FileNotFoundError):
        window.write_project_file()
    with open(filename, "rb") as fp:
        assert fp.read() == saved
    assert not (tmp_path / "project.cna.tmp").exists()


def assert_project_unchanged(window, model):
    assert window.appdata.project.cobra_py_model is model
    window.reset_gui_for_new_project.assert_not_called()


@pytest.mark.parametrize("arc_names, expected_kind", [
    (["model.sbml", "meta.json"], "critical"),         # no box_positions.json
    (["model.sbml", "box_positions.json"], "warning"),  # no meta.json
    (["box_positions.json", "meta.json"], "warning"),   # no model
], ids=["no_box_positions", "no_meta", "no_model"])
def test_open_incomplete_project(window, tmp_path, arc_names, expected_kind):
    model = window.appdata.project.cobra_py_model
    filename = str(tmp_path / "broken.cna")
    with ZipFile(filename, "w") as zip_obj:
        for name in arc_names:
            zip_obj.writestr(name, "{}")
    window.open_project(filename)
    assert [m[0] for m in window.messages] == [expected_kind]
    assert_project_unchanged(window, model)


def test_open_non_zip_file(window, tmp_path):
    model = window.appdata.project.cobra_py_model
    filename = tmp_path / "not_a_zip.cna"
    filename.write_text("this is not a ZIP file")
    window.open_project(str(filename))
    assert [m[0] for m in window.messages] == ["critical"]
    assert_project_unchanged(window, model)


@pytest.mark.parametrize("suffix", ["xml", "json"])
def test_model_export_round_trip(window, tmp_path, suffix):
    model = window.appdata.project.cobra_py_model
    path = str(tmp_path / ("model." + suffix))
    window.save_model(path, save_as_json=(suffix == "json"))
    assert window.messages == []  # ECC2 has no undefined compartments
    reread = CNApyModel.read_sbml_model(path) if suffix == "xml" else cobra.io.load_json_model(path)
    assert model_hash(reread) == model_hash(model)
    if suffix == "xml":
        # JSON export sorts the metabolites of each reaction alphabetically, which changes
        # stoichiometry_hash (it depends on the metabolite order), so only SBML is compared here
        assert stoichiometry_hash(reread).digest() == stoichiometry_hash(model).digest()
