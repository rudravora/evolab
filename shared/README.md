# shared/

Code and contract files shared between the backend, worker and experiments
code. Standard library only in this directory's `.py` files — nothing here
should require a third-party dependency, since both the backend and the
worker import it directly rather than over the network.

## signature.py

`normalize_error(text)` and `signature(text, libs=None)` — the
`error_fix` memory-entry signature described in AGENTS.md section 7
("Hash of error text with paths, hex and numbers stripped, plus library
names and versions"). Deterministic across machines/paths/platforms, so the
same underlying error always dedupes to the same `memory_entries` row
instead of inserting a duplicate.

**How the backend imports it:** the backend (`backend/`) and the worker
(`worker/`) are separate Python processes with separate dependency sets, but
both run from the same repo checkout, so `shared/` is importable by path
rather than as an installed package. Add the repo root to `sys.path` (or run
with `PYTHONPATH=<repo_root>`) and import normally:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

from shared.signature import signature

sig = signature(error_text, libs={"numpy": "1.26.4", "torch": "2.14.1"})
```

The Librarian (backend) calls this when writing or looking up an `error_fix`
memory entry; the Debugger agent's output flows through the Librarian, so
the Debugger itself does not need to import this module directly.
