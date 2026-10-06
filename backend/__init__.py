"""Makes `backend` importable as a package from the project root.

Two documented ways to start the server must both work:

    uvicorn backend.main:app --reload      # from the project root
    uvicorn main:app --reload              # from inside backend/

The modules under this directory import each other by top-level name
(`from ai.identification import ...`, `from matching import engine`), which is
what makes `uvicorn main:app` work from inside `backend/`. Putting this
directory on `sys.path` before the submodules load means the package-style
command resolves those same imports too - so neither form needs the other's
convention, and no module has to be rewritten.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
