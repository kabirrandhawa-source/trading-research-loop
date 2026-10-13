"""Sign Kalshi API requests with your API key. The key is read from disk into memory only;
it is never printed, logged, or written anywhere else.

config/.env:    KALSHI_API_KEY_ID=<key id>
key file:       config/kalshi_private_key.pem  (or set KALSHI_PRIVATE_KEY_PATH)
"""
import base64
import os
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "config" / ".env")


class MissingKey(RuntimeError):
    pass


def load():
    """Return (key_id, private_key). Raises MissingKey with a plain explanation if not set up."""
    key_id = os.getenv("KALSHI_API_KEY_ID", "").strip()
    path = Path(os.getenv("KALSHI_PRIVATE_KEY_PATH", "") or ROOT / "config" / "kalshi_private_key.pem")
    if not key_id:
        raise MissingKey("KALSHI_API_KEY_ID is not set in config/.env")
    if not path.exists():
        raise MissingKey(f"Kalshi private key file not found at {path}")
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except Exception as e:
        raise MissingKey(f"Could not read the Kalshi private key file ({type(e).__name__})") from None
    return key_id, key


def sign(key, message: str) -> str:
    data = message.encode()
    if isinstance(key, ed25519.Ed25519PrivateKey):
        sig = key.sign(data)
    else:
        sig = key.sign(data, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                         salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
    return base64.b64encode(sig).decode()


def headers(key_id, key, method, path):
    """Auth headers. The signed string is timestamp_ms + METHOD + path (no query string)."""
    ts = str(int(time.time() * 1000))
    return {"KALSHI-ACCESS-KEY": key_id, "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": sign(key, ts + method.upper() + path.split("?")[0])}
