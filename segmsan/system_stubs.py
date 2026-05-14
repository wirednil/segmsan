"""System procedure stubs loader.

Loads procedure signatures from data/system_procs.json and provides
ProcSummary objects for the interprocedural analyzer.
"""

from __future__ import annotations
import json
import os
from .interproc import ProcSummary

_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "system_procs.json")


def load_system_stubs() -> dict[str, ProcSummary]:
    if not os.path.isfile(_DATA_FILE):
        return {}
    with open(_DATA_FILE) as f:
        data = json.load(f)
    stubs: dict[str, ProcSummary] = {}
    for name, info in data.items():
        stubs[name.upper()] = ProcSummary(
            name=name,
            stores_refs_globally=info.get("stores_refs_globally", False),
        )
    return stubs


SYSTEM_PROC_STUBS: dict[str, ProcSummary] = load_system_stubs()
