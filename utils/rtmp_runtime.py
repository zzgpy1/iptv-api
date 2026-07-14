import glob
import os
import shutil
import subprocess
import sys
from functools import lru_cache


def find_nginx_executable() -> str | None:
    configured = os.getenv("IPTV_API_NGINX_PATH", "").strip()
    candidates = [
        configured,
        shutil.which("nginx"),
        "/opt/homebrew/bin/nginx",
        "/usr/local/bin/nginx",
    ]
    return next((path for path in candidates if path and os.path.isfile(path) and os.access(path, os.X_OK)), None)


def find_rtmp_module() -> str | None:
    configured = os.getenv("IPTV_API_NGINX_RTMP_MODULE", "").strip()
    patterns = [
        "/opt/homebrew/opt/*/modules/ngx_rtmp_module.so",
        "/usr/local/opt/*/modules/ngx_rtmp_module.so",
        "/opt/homebrew/lib/nginx/modules/ngx_rtmp_module.so",
        "/usr/local/lib/nginx/modules/ngx_rtmp_module.so",
    ]
    candidates = [configured]
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))
    return next((path for path in candidates if path and os.path.isfile(path)), None)


@lru_cache(maxsize=1)
def rtmp_runtime_status() -> dict:
    if sys.platform == "win32":
        return {"available": True, "executable": "", "module": "", "error_code": ""}
    if sys.platform != "darwin":
        return {"available": False, "executable": "", "module": "", "error_code": "unsupported_platform"}
    executable = find_nginx_executable()
    if not executable:
        return {"available": False, "executable": "", "module": "", "error_code": "nginx_missing"}
    module = find_rtmp_module()
    try:
        process = subprocess.run(
            [executable, "-V"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        build_info = f"{process.stdout}\n{process.stderr}".lower()
    except Exception:
        build_info = ""
    if not module and "rtmp" not in build_info:
        return {"available": False, "executable": executable, "module": "", "error_code": "rtmp_module_missing"}
    return {"available": True, "executable": executable, "module": module or "", "error_code": ""}
