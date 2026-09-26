"""SLAIFI application package integrated into the SLAI applications namespace.

SLAIFI is cloned at::

    SLAI/applications/slaifi/

The application currently keeps its implementation below ``backend/slaifi``.
This package root exposes that implementation without modifying ``sys.path``,
changing the working directory, or requiring an editable install.

The compatibility alias preserves the existing internal ``from slaifi...``
imports until those imports are converted to package-relative imports.
"""

from __future__ import annotations

import sys
from pathlib import Path


__version__ = "0.3.0"

_APPLICATION_ROOT = Path(__file__).resolve().parent
_BACKEND_PACKAGE = _APPLICATION_ROOT / "backend" / "slaifi"

# Make applications.slaifi behave as the package root while the implementation
# remains physically under backend/slaifi. This modifies only this package's
# search path; it does not mutate Python's global sys.path.
if _BACKEND_PACKAGE.is_dir():
    backend_path = str(_BACKEND_PACKAGE)
    if backend_path not in __path__:
        __path__.append(backend_path)

# Existing SLAIFI modules currently import one another through ``slaifi.*``.
# Bind that historical package name to this integrated application package so
# every submodule resolves from one package instance.
sys.modules["slaifi"] = sys.modules[__name__]


__all__ = ["__version__"]
