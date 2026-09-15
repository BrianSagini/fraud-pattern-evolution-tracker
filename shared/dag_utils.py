"""Load a project's pipeline.py by file path rather than dotted import.

Project directories are numbered (01_climate_risk_business_impact, ...) so
they aren't valid Python package names -- this sidesteps that, and gives
each project's module a unique name in sys.modules so the dag-processor
(which imports every DAG file in one process) never collides two projects'
same-named `pipeline` module.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PROJECTS_ROOT = Path("/opt/airflow/projects")


def load_project_pipeline(project_dir: str, unique_name: str) -> ModuleType:
    module_path = PROJECTS_ROOT / project_dir / "pipeline.py"
    spec = importlib.util.spec_from_file_location(unique_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = module
    spec.loader.exec_module(module)
    return module
