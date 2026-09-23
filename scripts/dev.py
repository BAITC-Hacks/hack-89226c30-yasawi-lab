"""Start the existing FastAPI and Vite applications with one command."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]


def read_env(path: Path) -> dict[str, str]:
    """Read literal KEY=value settings; never execute or interpolate file contents."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not key.isidentifier():
            raise ValueError(f"{path.name}:{number}: expected KEY=value")
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f"{path.name}:{number}: unterminated quoted value")
            value = value[1:-1]
        values[key] = value
    return values


def configuration() -> tuple[dict[str, str], str, int, str, str, int]:
    env = {**read_env(ROOT / ".env"), **os.environ}
    # Explicit shell/root settings take precedence, as they do in Vite.
    for key, value in read_env(ROOT / "frontend" / ".env.local").items():
        env.setdefault(key, value)
    backend_host = env.get("BACKEND_HOST", "127.0.0.1")
    backend_port = int(env.get("BACKEND_PORT", "8000"))
    if not 1 <= backend_port <= 65535:
        raise ValueError("BACKEND_PORT must be between 1 and 65535")
    origin = env.setdefault("FRONTEND_ORIGIN", "http://127.0.0.1:5173").rstrip("/")
    frontend = urlsplit(origin)
    if (frontend.scheme != "http" or not frontend.hostname or frontend.username
            or frontend.password or frontend.path or frontend.query or frontend.fragment):
        raise ValueError("For this local launcher, FRONTEND_ORIGIN must be one HTTP origin, such as http://127.0.0.1:5173")
    frontend_port = frontend.port or 80
    env.setdefault("VITE_API_BASE_URL", f"http://127.0.0.1:{backend_port}")
    api_url = urlsplit(env["VITE_API_BASE_URL"])
    if api_url.scheme not in ("http", "https") or not api_url.netloc:
        raise ValueError("VITE_API_BASE_URL must be a browser-reachable HTTP(S) API base URL")
    source_path = str(ROOT / "backend" / "src")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (source_path, env.get("PYTHONPATH"))))
    env["PYTHONUNBUFFERED"] = "1"
    return env, backend_host, backend_port, origin, frontend.hostname, frontend_port


def stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        # Only terminate the child process tree created by this launcher.
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate configuration and dependencies without starting servers")
    args = parser.parse_args()
    try:
        env, host, port, origin, frontend_host, frontend_port = configuration()
        node = shutil.which("node")
        if not node:
            raise ValueError("Node.js is missing from PATH; install Node.js 20.19+ (22.12+ recommended)")
        vite = ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
        if not vite.is_file():
            raise ValueError("Frontend dependencies are missing; run npm ci --prefix frontend")
        check = subprocess.run([sys.executable, "-c", "import fastapi, uvicorn, agentic_forecast.api"],
                               cwd=ROOT / "backend", env=env, capture_output=True, text=True)
        if check.returncode:
            raise ValueError("Backend dependencies could not load; use this Python to run: python -m pip install -e \"./backend[test]\"\n" + check.stderr.strip())
    except (ValueError, OSError) as exc:
        print(f"Development setup error: {exc}", file=sys.stderr)
        return 1
    print(f"Frontend: {origin}", flush=True)
    print(f"Browser API base: {env['VITE_API_BASE_URL']}", flush=True)
    print(f"Backend binds: {host}:{port}", flush=True)
    if args.check:
        print("Configuration and dependencies are ready.")
        return 0
    children: list[subprocess.Popen] = []
    try:
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        children.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "agentic_forecast.api:app",
                                          "--host", host, "--port", str(port)],
                                         cwd=ROOT / "backend", env=env, **options))
        children.append(subprocess.Popen([node, str(vite), "--host", frontend_host,
                                          "--port", str(frontend_port), "--strictPort"],
                                         cwd=ROOT / "frontend", env=env, **options))
        print("Press Ctrl+C to stop both servers.", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.25)
        code = next(child.returncode for child in children if child.poll() is not None)
        print(f"A development server exited ({code}); stopping the other server.", file=sys.stderr)
        return code or 1
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        print(f"Could not start development servers: {exc}", file=sys.stderr)
        return 1
    finally:
        for child in reversed(children):
            stop(child)


if __name__ == "__main__":
    raise SystemExit(main())
