import os
from pathlib import Path


def find_project_root() -> Path:
    return Path(os.getcwd()).resolve()
