import ipaddress
import time
import xml.etree.ElementTree as ET

import requests
import sys

import utils.constants as constants
from utils.channel_repository import result_metadata_map
from utils.config import config
from utils.rtmp_runtime import rtmp_runtime_status


def _number(element, path: str, default=0):
    value = element.findtext(path)
    try:
        return float(value) if "." in str(value) else int(value)
    except (AttributeError, TypeError, ValueError):
        return default


def _duration(milliseconds) -> str:
    seconds = max(0, int(float(milliseconds or 0) / 1000))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _masked_address(value: str | None) -> str:
    if not value:
        return ""
    host, separator, port = value.rpartition(":")
    candidate = host.strip("[]") if separator else value
    try:
        address = ipaddress.ip_address(candidate)
        if address.version == 4:
            parts = candidate.split(".")
            masked = ".".join([parts[0], parts[1], "*", "*"])
        else:
            masked = f"{':'.join(candidate.split(':')[:3])}:*"
        return f"{masked}:{port}" if separator and port else masked
    except ValueError:
        return value


def parse_rtmp_stats(content: bytes | str, db_path: str = constants.channel_results_path) -> dict:
    root = ET.fromstring(content)
    stream_elements = root.findall("./server/application/live/stream")
    keys = [element.findtext("name", "") for element in stream_elements]
    metadata = result_metadata_map(db_path, keys)
    streams = []
    for element in stream_elements:
        result_key = element.findtext("name", "")
        meta = metadata.get(result_key, {})
        video = element.find("./meta/video")
        audio = element.find("./meta/audio")
        width = _number(video, "width") if video is not None else 0
        height = _number(video, "height") if video is not None else 0
        clients = []
        for client in element.findall("client"):
            clients.append({
                "id": client.findtext("id", ""),
                "state": "publishing" if client.find("publishing") is not None else "playing",
                "address": _masked_address(client.findtext("address")),
                "dropped": _number(client, "dropped"),
                "timestamp": client.findtext("timestamp", ""),
                "av_sync": _number(client, "avsync"),
                "uptime": _duration(_number(client, "time")),
            })
        streams.append({
            "result_key": result_key,
            "name": result_key,
            "channel_key": meta.get("channel_key"),
            "category": meta.get("category") or "",
            "channel_name": meta.get("name") or result_key,
            "url": meta.get("url"),
            "state": "active" if element.find("active") is not None else "idle",
            "active": element.find("active") is not None,
            "clients": _number(element, "nclients"),
            "bw_in": _number(element, "bw_in"),
            "bw_out": _number(element, "bw_out"),
            "bytes_in": _number(element, "bytes_in"),
            "bytes_out": _number(element, "bytes_out"),
            "video_codec": video.findtext("codec", "") if video is not None else "",
            "audio_codec": audio.findtext("codec", "") if audio is not None else "",
            "resolution": f"{width}x{height}" if width and height else "",
            "fps": _number(video, "frame_rate") if video is not None else 0,
            "uptime": _duration(_number(element, "time")),
            "client_details": clients,
        })
    return {
        "available": True,
        "sampled_at": time.time(),
        "uptime": _duration(_number(root, "uptime") * 1000),
        "accepted": _number(root, "naccepted"),
        "bw_in": _number(root, "bw_in"),
        "bw_out": _number(root, "bw_out"),
        "bytes_in": _number(root, "bytes_in"),
        "bytes_out": _number(root, "bytes_out"),
        "streams": streams,
    }


def fetch_rtmp_snapshot(timeout: float = 1.5) -> dict:
    url = f"http://127.0.0.1:{config.nginx_http_port}/stat"
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return parse_rtmp_stats(response.content)
    except Exception as exc:
        status = rtmp_runtime_status() if sys.platform == "darwin" else {}
        return {
            "available": False,
            "sampled_at": time.time(),
            "streams": [],
            "error": str(exc),
            "error_code": status.get("error_code") or "connection",
        }
