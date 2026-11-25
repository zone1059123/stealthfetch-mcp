"""Polar license validation and atomic, local UTC quota accounting."""

import hashlib
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

FREE_DAILY_LIMIT = 20
CACHE_SECONDS = 7 * 24 * 60 * 60
# Copy your organization ID from the Polar.sh dashboard.
DEFAULT_POLAR_ORG_ID = "dfb77aae-d71f-4b12-8d56-a6039e6cd37c"
UPGRADE_URL = "https://buy.polar.sh/polar_cl_Vy3OoCLPPrdTfUPFqcRvLAwkJw70J82gMZlJS2sxJ8b"
POLAR_VALIDATE = "https://api.polar.sh/v1/customer-portal/license-keys/validate"


@dataclass(frozen=True)
class Access:
    allowed: bool
    tier: str
    remaining: int | None


class LicenseManager:
    def __init__(self, db_path: Path, key: str = "", organization_id: str = ""):
        self.db_path = db_path
        self.key = key.strip()
        self.organization_id = organization_id.strip()

    @classmethod
    def from_environment(cls):
        path = os.getenv("STEALTHFETCH_DB") or Path.home() / ".stealthfetch-mcp/state.sqlite3"
        return cls(
            Path(path).expanduser(),
            os.getenv("STEALTHFETCH_LICENSE_KEY", ""),
            os.getenv("POLAR_ORGANIZATION_ID", DEFAULT_POLAR_ORG_ID),
        )

    def _verify(self, now: datetime) -> float:
        try:
            response = httpx.post(
                POLAR_VALIDATE,
                json={"key": self.key, "organization_id": self.organization_id},
                timeout=5,
            )
            if response.status_code != 200:
                return 0
            result = response.json()
            if not isinstance(result, dict) or result.get("status") != "granted":
                return 0
            expiry = now.timestamp() + CACHE_SECONDS
            if result.get("expires_at"):
                if not isinstance(result["expires_at"], str):
                    return 0
                license_expiry = datetime.fromisoformat(result["expires_at"].replace("Z", "+00:00"))
                if license_expiry.tzinfo is None:
                    return 0
                expiry = min(expiry, license_expiry.timestamp())
            return expiry
        except (httpx.HTTPError, ValueError, TypeError, OverflowError):
            return 0

    def _has_pro(self, db: sqlite3.Connection, now: datetime) -> bool:
        if not self.key or self.organization_id in {"", "YOUR_POLAR_ORG_ID"}:
            return False

        fingerprint = hashlib.sha256(
            f"{self.organization_id}\0{self.key}".encode()
        ).hexdigest()
        row = db.execute(
            "SELECT valid_until FROM license_cache WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
        if row and row[0] > now.timestamp():
            return True
        expiry = self._verify(now)
        if expiry <= datetime.now(timezone.utc).timestamp():
            return False

        with db:
            db.execute(
                "INSERT OR REPLACE INTO license_cache VALUES (?, ?)", (fingerprint, expiry)
            )
        return True

    def acquire(self, *, pro_only: bool = False) -> Access:
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with closing(sqlite3.connect(self.db_path, timeout=10)) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS quota (day TEXT PRIMARY KEY, used INTEGER NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS license_cache "
                "(fingerprint TEXT PRIMARY KEY, valid_until REAL NOT NULL)"
            )
            now = datetime.now(timezone.utc)
            if self._has_pro(db, now):
                return Access(True, "pro", None)
            if pro_only:
                return Access(False, "free", None)

            with db:
                row = db.execute(
                    """
                    INSERT INTO quota (day, used) VALUES (?, 1)
                    ON CONFLICT(day) DO UPDATE SET used = used + 1
                    WHERE used < ?
                    RETURNING used
                    """,
                    (now.date().isoformat(), FREE_DAILY_LIMIT),
                ).fetchone()
            if row is None:
                return Access(False, "free", 0)
            return Access(True, "free", FREE_DAILY_LIMIT - row[0])
