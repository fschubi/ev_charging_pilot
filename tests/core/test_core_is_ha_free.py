"""§4.3: the core package must never import Home Assistant."""

import ast
from pathlib import Path

CORE = Path(__file__).parents[2] / "custom_components" / "ev_charging_pilot" / "core"


def test_core_has_no_homeassistant_imports():
    offenders = []
    for path in CORE.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            offenders += [f"{path.name}: {n}" for n in names if n.split(".")[0] == "homeassistant"]
    assert offenders == []
