from __future__ import annotations

import importlib
import importlib.util
import inspect
import pkgutil
import sys
from pathlib import Path
from typing import Optional

from reaper.modules.blueprint import ReaperModule

_cache: dict[str, type[ReaperModule]] | None = None


def load_modules(reload: bool = False) -> dict[str, type[ReaperModule]]:
    global _cache
    if _cache is not None and not reload:
        return _cache

    modules: dict[str, type[ReaperModule]] = {}
    pkg_dir = Path(__file__).parent

    for _, mod_name, _ in pkgutil.iter_modules([str(pkg_dir)]):
        if mod_name in ("blueprint", "loader"):
            continue
        full_name = f"reaper.modules.{mod_name}"
        try:
            if reload and full_name in sys.modules:
                mod = importlib.reload(sys.modules[full_name])
            else:
                mod = importlib.import_module(full_name)

            for _, cls in inspect.getmembers(mod, inspect.isclass):
                if (
                    issubclass(cls, ReaperModule)
                    and cls is not ReaperModule
                    and cls.__module__ == full_name
                ):
                    modules[cls.name] = cls
        except Exception as exc:
            print(f"  [!] Failed to load module {mod_name!r}: {exc}")

    _cache = modules
    return modules


def get_module(name: str) -> Optional[type[ReaperModule]]:
    return load_modules().get(name)
