"""Print an OWNER_PASSWORD_HASH line for .env. The password is read without echo and never stored.

Run from backend/:  python scripts/hash_password.py
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.security import hash_password  # noqa: E402

pw = getpass.getpass("Owner password: ")
if len(pw) < 12:
    sys.exit("Use at least 12 characters.")
if getpass.getpass("Repeat: ") != pw:
    sys.exit("Passwords do not match.")
print(f"OWNER_PASSWORD_HASH={hash_password(pw)}")
