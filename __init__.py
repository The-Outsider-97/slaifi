"""SLAIFI application package integrated into the SLAI applications namespace.

SLAIFI is cloned at::

    SLAI/applications/slaifi/

The implementation remains physically below ``backend/slaifi`` so standalone
packaging and the SLAI application layout can share one source tree. This
package root exposes that implementation without changing the process working
directory or mutating Python's global ``sys.path``.
"""

from __future__ import annotations

import sys
from pathlib import Path

__version__ = "0.3.0"

_APPLICATION_ROOT = Path(__file__).resolve().parent
_BACKEND_PACKAGE = _APPLICATION_ROOT / "backend" / "slaifi"

if _BACKEND_PACKAGE.is_dir():
    backend_path = str(_BACKEND_PACKAGE)
    if backend_path not in __path__:
        __path__.append(backend_path)

# Internal modules currently use the standalone package name ``slaifi``.
# When hosted as ``applications.slaifi``, bind that name to this same package
# instance so submodules are not imported twice under different identities.
sys.modules.setdefault("slaifi", sys.modules[__name__])

__all__ = ["__version__"]
