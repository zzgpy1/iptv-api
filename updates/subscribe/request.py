import asyncio
from collections import defaultdict
from logging import INFO
from time import time
import sys

from aiohttp import ClientSession, TCPConnector
from tqdm.asyncio import tqdm_asyncio

import utils.constants as constants
from utils.channel import format_channel_name
from utils.config import config
from utils.i18n import t
from utils.requests.async_tools import fetch_first, merge_headers
from utils.tools import (
    get_pbar_remaining,
    get_name_value,
    get_m3u_epg_urls,
    get_logger,
    get_request_url_candidates,
    save_url_content,
    close_logger_handlers,
    disable_urls_in_file,
)


def _channel_item_key(item):
    return (
        item.get("url"),
        tuple(sorted((item.get("headers") or {}).items())),
        item.get("tvg_logo"),
        item.get("extra_info", ""),
    )


def _merge_channel_results(target, source, seen):
    for name, items in source.items():
        target_items = target.setdefault(name, [])
        name_seen = seen.setdefault(name, set())
        for item in items:
            key = _channel_item_key(item)
            if key in name_seen:
                continue
            name_seen.add(key)
            target_items.append(item)


async def get_channels_by_subscribe_urls(
        urls,
        names=None,
        whitelist=None,
        callback=None,
        epg_urls_out=None,
        pause_wait=None,
):
    normalized_names = {format_channel_name(name) for name in (names or []) if name}
    if whitelist:
        index_map = {url: index for index, url in enumerate(whitelist)}

        def sort_key(item):
            key = item['url'] if isinstance(item, dict) else item
            return index_map.get(key, len(whitelist))

        urls.sort(key=sort_key)

    subscribe_urls_len = len(urls)
    pbar = tqdm_asyncio(
        total=subscribe_urls_len,
        desc=t("pbar.getting_name").format(name=t("name.subscribe")),
        file=sys.stdout,
        mininterval=1.0,
        miniters=1,
        dynamic_ncols=False,
    )
    start_time = time()
    mode_name = t("name.subscribe")
    if callback:
        callback(t("pbar.getting_name").format(name=mode_name), 0)

    logger = get_logger(constants.unmatch_log_path, level=INFO, init=True)
    request_timeout = config.request_timeout
    open_headers = config.open_headers
    open_unmatch_category = config.open_unmatch_category
    open_auto_disable_source = config.open_auto_disable_source
    open_subscribe_epg = config.open_subscribe_epg
    disabled_urls = set()
    discovered_epg_urls = set()
    unmatched_logged = 0
    unmatched_log_limit = 10000
    fetch_workers = config.performance_settings.fetch_workers
    semaphore = asyncio.Semaphore(fetch_workers)

    def mark_disabled(source_url: str, reason: str):
        if not open_auto_disable_source or not source_url:
            return
        disabled_urls.add(source_url)
        print(t("msg.auto_disable_source").format(name=mode_name, url=source_url, reason=reason), flush=True)

    def advance_progress():
        pbar.update()
        if callback:
            callback(
                t("msg.progress_desc").format(
                    name=f"{t('pbar.get')}{mode_name}",
                    remaining_total=subscribe_urls_len - pbar.n,
                    item_name=mode_name,
                    remaining_time=get_pbar_remaining(n=pbar.n, total=pbar.total, start_time=start_time),
                ),
                int((pbar.n / subscribe_urls_len) * 100),
            )

    async def process_subscribe_channels(session: ClientSession, subscribe_info: str | dict):
        nonlocal unmatched_logged
        subscribe_url = subscribe_info.get('url') if isinstance(subscribe_info, dict) else subscribe_info
        source_url = (
            subscribe_info.get('source_url', subscribe_url)
            if isinstance(subscribe_info, dict)
            else subscribe_url
        )
        headers = subscribe_info.get('headers') if isinstance(subscribe_info, dict) else None
        channels = defaultdict(list)
        channel_seen = defaultdict(set)
        in_whitelist = whitelist and subscribe_url in whitelist
        disable_reason = None
        cancelled = False
        try:
            content = ""
            try:
                if pause_wait:
                    await pause_wait()
                async with semaphore:
                    if pause_wait:
                        await pause_wait()
                    content = await fetch_first(
                        session,
                        get_request_url_candidates(subscribe_url),
                        name=subscribe_url,
                        headers=merge_headers(headers),
                        timeout=request_timeout,
                        raise_for_status=False,
                        require_content=True,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(exc, flush=True)
                disable_reason = t("msg.auto_disable_request_failed")

            if content:
                try:
                    save_url_content('subscribe', subscribe_url, content)
                except Exception:
                    pass
                m3u_type = "#EXTM3U" in content
                if open_subscribe_epg and m3u_type:
                    discovered_epg_urls.update(get_m3u_epg_urls(content))
                data = await asyncio.to_thread(
                    get_name_value,
                    content,
                    pattern=constants.multiline_m3u_pattern if m3u_type else constants.multiline_txt_pattern,
                    open_headers=open_headers if m3u_type else False,
                )
                for index, item in enumerate(data):
                    if index % 1000 == 0:
                        if pause_wait:
                            await pause_wait()
                        else:
                            await asyncio.sleep(0)
                    data_name = item.get("name", "").strip()
                    url = item.get("value", "").strip()
                    if not data_name or not url:
                        continue
                    name = format_channel_name(data_name)
                    if normalized_names and name not in normalized_names:
                        if unmatched_logged < unmatched_log_limit:
                            logger.info(f"{data_name},{url}")
                            unmatched_logged += 1
                        if not open_unmatch_category:
                            continue
                    url, _, extra_info = url.partition("$")
                    item_headers = {**(headers or {}), **(item.get("headers") or {})}
                    value = {
                        "url": url,
                        "headers": item_headers or None,
                        "tvg_logo": item.get("tvg_logo") or None,
                        "extra_info": extra_info,
                    }
                    if in_whitelist:
                        value["origin"] = "whitelist"
                    key = _channel_item_key(value)
                    if key not in channel_seen[name]:
                        channel_seen[name].add(key)
                        channels[name].append(value)
                if not channels and not disable_reason:
                    disable_reason = t("msg.auto_disable_no_match")
            elif not disable_reason:
                disable_reason = t("msg.auto_disable_empty_content")
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception as exc:
            print(t("msg.error_name_info").format(name=subscribe_url, info=exc), flush=True)
            if not disable_reason:
                disable_reason = t("msg.auto_disable_request_failed")
        finally:
            if disable_reason:
                mark_disabled(source_url, disable_reason)
            if not cancelled:
                advance_progress()
        return channels

    tasks = []
    try:
        async with ClientSession(
                connector=TCPConnector(limit=fetch_workers),
                trust_env=True,
        ) as session:
            tasks = [
                asyncio.create_task(process_subscribe_channels(session, subscribe_url))
                for subscribe_url in urls
            ]
            try:
                results = await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

        subscribe_results = defaultdict(list)
        subscribe_seen = defaultdict(set)
        for channels in results:
            _merge_channel_results(subscribe_results, channels, subscribe_seen)

        active_count = len(urls)
        disabled_count = 0
        if disabled_urls:
            counts = disable_urls_in_file(constants.subscribe_path, disabled_urls)
            active_count = counts["active"]
            disabled_count = counts["disabled"]
        print(
            t("msg.auto_disable_source_done").format(
                name=mode_name,
                active_count=active_count,
                disabled_count=disabled_count,
            ),
            flush=True,
        )
        if epg_urls_out is not None and discovered_epg_urls:
            epg_urls_out.update(discovered_epg_urls)
            print(t("msg.subscribe_epg_found").format(count=len(discovered_epg_urls)), flush=True)
        return subscribe_results
    finally:
        pbar.close()
        close_logger_handlers(logger)
