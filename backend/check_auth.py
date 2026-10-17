"""Verify Supabase access-token validation without needing a real account.

Run from the project root:

    .venv/Scripts/python backend/check_auth.py

It stands up a throwaway JWKS endpoint, mints ES256 tokens against it, and
checks that backend.main.decode_supabase_token accepts only valid ones. It then
confirms that the JWKS URL configured in .env is reachable and parsable.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

TEST_PORT = 8123
TEST_KID = "hyperion-test-key"
FAILURES: list[str] = []


def base64url_uint(value: int) -> str:
    import base64

    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def jwk_for(key: ec.EllipticCurvePrivateKey, kid: str) -> dict[str, str]:
    numbers = key.public_key().public_numbers()
    return {
        "alg": "ES256",
        "crv": "P-256",
        "ext": True,
        "key_ops": ["verify"],
        "kid": kid,
        "kty": "EC",
        "use": "sig",
        "x": base64url_uint(numbers.x),
        "y": base64url_uint(numbers.y),
    }


def serve_jwks(jwk: dict[str, str]) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = json.dumps({"keys": [jwk]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", TEST_PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def expect(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS  {name}")
    else:
        print(f"FAIL  {name} {detail}")
        FAILURES.append(name)


def main() -> int:
    signing_key = ec.generate_private_key(ec.SECP256R1())
    jwk = jwk_for(signing_key, TEST_KID)
    server = serve_jwks(jwk)
    os.environ["SUPABASE_JWKS_URL"] = f"http://127.0.0.1:{TEST_PORT}/jwks.json"
    os.environ.pop("SUPABASE_JWT_SECRET", None)

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from backend.main import decode_supabase_token, jwks_client  # imported after env is set

    now = datetime.now(timezone.utc)
    valid = jwt.encode(
        {"sub": "user-123", "aud": "authenticated", "email": "trader@example.com", "exp": now + timedelta(hours=1)},
        signing_key,
        algorithm="ES256",
        headers={"kid": TEST_KID},
    )
    try:
        claims = decode_supabase_token(valid)
        expect("valid ES256 token is accepted", claims.get("sub") == "user-123", str(claims))
    except Exception as exc:  # noqa: BLE001
        expect("valid ES256 token is accepted", False, f"raised {exc}")

    expired = jwt.encode(
        {"sub": "user-123", "aud": "authenticated", "exp": now - timedelta(minutes=5)},
        signing_key,
        algorithm="ES256",
        headers={"kid": TEST_KID},
    )
    try:
        decode_supabase_token(expired)
        expect("expired token is rejected", False, "no exception raised")
    except Exception as exc:  # noqa: BLE001
        expect("expired token is rejected", "expired" in str(exc).lower(), str(exc))

    other_key = ec.generate_private_key(ec.SECP256R1())
    forged = jwt.encode(
        {"sub": "attacker", "aud": "authenticated", "exp": now + timedelta(hours=1)},
        other_key,
        algorithm="ES256",
        headers={"kid": TEST_KID},
    )
    try:
        decode_supabase_token(forged)
        expect("token signed by the wrong key is rejected", False, "no exception raised")
    except Exception as exc:  # noqa: BLE001
        expect("token signed by the wrong key is rejected", True, str(exc))

    wrong_audience = jwt.encode(
        {"sub": "user-123", "aud": "anon", "exp": now + timedelta(hours=1)},
        signing_key,
        algorithm="ES256",
        headers={"kid": TEST_KID},
    )
    try:
        decode_supabase_token(wrong_audience)
        expect("wrong audience is rejected", False, "no exception raised")
    except Exception as exc:  # noqa: BLE001
        expect("wrong audience is rejected", True, str(exc))

    server.shutdown()

    # Now check the JWKS endpoint configured in .env is actually usable.
    os.environ.pop("SUPABASE_JWKS_URL", None)
    os.environ.pop("SUPABASE_URL", None)
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)
    try:
        key_set = jwks_client().get_jwk_set()
        algorithms = sorted({key.algorithm_name for key in key_set.keys if key.algorithm_name})
        expect("configured Supabase JWKS is reachable", len(key_set.keys) > 0, "no keys returned")
        print(f"      configured JWKS algorithms: {algorithms}")
    except Exception as exc:  # noqa: BLE001
        expect("configured Supabase JWKS is reachable", False, str(exc))

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed: {', '.join(FAILURES)}")
        return 1
    print("All auth checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
