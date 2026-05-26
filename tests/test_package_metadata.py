from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_metadata_marks_alpha_mit_and_zope5_compatible():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]

    assert project["version"] == "0.1.0a2"
    assert project["requires-python"] == ">=3.8"
    assert project["license"]["text"] == "MIT"
    assert "Development Status :: 3 - Alpha" in project["classifiers"]
    assert "Zope>=5.0" in project["dependencies"]
    assert "Products.PluggableAuthService>=2.0" in project["dependencies"]
    assert "Products.ZSQLMethods" in project["dependencies"]
    assert "segno" in project["dependencies"]


def test_setup_py_keeps_legacy_buildout_metadata_in_sync():
    text = (ROOT / "setup.py").read_text(encoding="utf-8")

    assert 'version="0.1.0a2"' in text
    assert 'license="MIT"' in text
    assert 'python_requires=">=3.8"' in text
    assert '"Zope>=5.0"' in text
    assert '"Products.PluggableAuthService>=2.0"' in text


def test_mit_license_file_is_present():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")

    assert text.startswith("MIT License")
    assert "Rune Fredriksen" in text
