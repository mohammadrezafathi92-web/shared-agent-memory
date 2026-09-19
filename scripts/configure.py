"""Create local configuration without overwriting existing secrets."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
password = secrets.token_hex(24)
try:
    fd = os.open(root / ".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit(".env already exists; left unchanged.") from None
with os.fdopen(fd, "w") as f:
    f.write(
        f"POSTGRES_PASSWORD={password}\nMEMORY_PORT=8765\n"
        f"MEMORY_DATABASE_URL=postgresql://memory:{password}@127.0.0.1:55432/memory\n"
    )
print("Created private .env. Start with: docker compose up --build -d")
