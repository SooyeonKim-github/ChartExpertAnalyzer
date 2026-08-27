from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "scripts" / "build_liquidity_universe.py"
DEFAULT_KRX_TIMEOUT = 60.0
DEFAULT_NETWORK_RETRIES = 3


def _read_float_env(name: str, default: float) -> float:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _read_int_env(name: str, default: int) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _install_krx_timeout_override(timeout_seconds: float) -> None:
    """Raise pykrx's hard-coded 15 second KRX timeout without editing site-packages."""
    session_cls = requests.sessions.Session
    original = session_cls.request

    if getattr(original, "_chart_expert_krx_timeout_override", False):
        return

    def request_with_krx_timeout(self, method, url, *args, **kwargs):
        if "data.krx.co.kr" in str(url).lower():
            current = kwargs.get("timeout")
            if current is None:
                kwargs["timeout"] = timeout_seconds
            elif isinstance(current, (int, float)) and float(current) < timeout_seconds:
                kwargs["timeout"] = timeout_seconds
        return original(self, method, url, *args, **kwargs)

    request_with_krx_timeout._chart_expert_krx_timeout_override = True
    request_with_krx_timeout._chart_expert_original_request = original
    session_cls.request = request_with_krx_timeout


def _purge_partial_pykrx_imports() -> None:
    """Remove partially imported pykrx modules after a network failure so retry is clean."""
    for name in list(sys.modules):
        if name == "pykrx" or name.startswith("pykrx."):
            sys.modules.pop(name, None)


def _load_builder_module():
    spec = importlib.util.spec_from_file_location("chart_expert_liquidity_builder", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Liquidity builder를 불러올 수 없습니다: {BUILDER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    timeout_seconds = _read_float_env("KRX_HTTP_TIMEOUT", DEFAULT_KRX_TIMEOUT)
    retries = _read_int_env("KRX_NETWORK_RETRIES", DEFAULT_NETWORK_RETRIES)

    _install_krx_timeout_override(timeout_seconds)
    builder = _load_builder_module()

    print(
        f"[LIQUIDITY] KRX network guard: timeout={timeout_seconds:g}s, "
        f"network retries={retries}"
    )

    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return int(builder.main())
        except requests.exceptions.RequestException as exc:
            last_exc = exc
        except TimeoutError as exc:
            last_exc = exc

        if attempt >= retries:
            break

        print(
            f"[WARN] KRX network/login request failed "
            f"({attempt}/{retries}): {type(last_exc).__name__}: {last_exc}"
        )
        print(f"[WARN] {attempt * 3}초 후 KRX 연결을 다시 시도합니다...")
        _purge_partial_pykrx_imports()
        time.sleep(attempt * 3)

    raise RuntimeError(
        f"KRX 연결이 {retries}회 연속 실패했습니다. "
        f"data.krx.co.kr 접속 상태를 확인하세요. "
        f"필요하면 KRX_HTTP_TIMEOUT 환경변수로 timeout을 늘릴 수 있습니다."
    ) from last_exc


if __name__ == "__main__":
    raise SystemExit(main())
