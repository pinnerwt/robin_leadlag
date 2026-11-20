"""Head-to-head arrival race for Binance Spot best bid/ask on one host.

Feeds: JSON bookTicker on data-stream.binance.vision and stream.binance.com,
and SBE bestBidAsk on stream-sbe.binance.com. Updates are matched by book
update id and timed on one monotonic clock. Read-only market data; no orders.

    uv run --with websockets python -u scripts/binance_sbe_ab.py

SBE needs an Ed25519 API key (key only, no signature) in .env:
    BINANCE_SBE_API_KEY=...
Env: CAPTURE_SECS (default 120), SYM (default ethusdt), CONNS (default 2),
ENV_FILE (default .env next to the repo root). The key is never printed.
stream.binance.com and stream-sbe.binance.com return HTTP 451 from US hosts.
"""
import asyncio
import itertools
import json
import os
from pathlib import Path
import ssl
import statistics
import struct
import time

import websockets

DUR = float(os.environ.get('CAPTURE_SECS', '120'))
SYM = os.environ.get('SYM', 'ethusdt').lower()
CONNS = int(os.environ.get('CONNS', '2'))
ENV_FILE = Path(os.environ.get('ENV_FILE', Path(__file__).resolve().parent.parent / '.env'))
HEADER = struct.Struct('<HHHH')            # blockLength, templateId, schemaId, version
BEST_BID_ASK = struct.Struct('<qqbbqqqq')  # eventTime us, bookUpdateId, exponents, bid/ask px+qty
BEST_BID_ASK_ID = 10001


def api_key():
    key = os.environ.get('BINANCE_SBE_API_KEY', '')
    if not key and ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            name, sep, value = line.partition('=')
            if sep and name.strip() == 'BINANCE_SBE_API_KEY':
                key = value.strip().strip('"').strip("'")
    return key


def decode_json(raw):
    if not isinstance(raw, str):
        return None
    return json.loads(raw).get('u'), None


def decode_sbe(raw):
    if isinstance(raw, str) or len(raw) < HEADER.size + BEST_BID_ASK.size:
        return None
    block, template, _schema, _version = HEADER.unpack_from(raw)
    if template != BEST_BID_ASK_ID or block < BEST_BID_ASK.size:
        return None
    event_us, update_id = BEST_BID_ASK.unpack_from(raw, HEADER.size)[:2]
    return update_id, event_us


FEEDS = {
    'vision': (f'wss://data-stream.binance.vision:443/ws/{SYM}@bookTicker', decode_json, {}),
    'stream': (f'wss://stream.binance.com:9443/ws/{SYM}@bookTicker', decode_json, {}),
}
first = {name: {} for name in ('vision', 'stream', 'sbe')}
counts = {name: 0 for name in first}
event_lag_us = []
errors = []
tls = ssl.create_default_context()


async def run(name, url, decode, headers, stop):
    try:
        async with websockets.connect(url, ssl=tls, additional_headers=headers, ping_interval=None,
                                      max_queue=None, open_timeout=15) as ws:
            while not stop.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                mono = time.monotonic_ns()
                wall = time.time_ns()
                row = decode(raw)
                if not row or row[0] is None:
                    continue
                update_id, event_us = row
                counts[name] += 1
                if update_id not in first[name]:
                    first[name][update_id] = mono
                    if event_us:
                        event_lag_us.append(wall / 1000 - event_us)
    except Exception as exc:
        errors.append(f'{name}: {type(exc).__name__}: {exc}')


def summary(label, a, b):
    """Positive = `a` arrived first."""
    common = first[a].keys() & first[b].keys()
    if not common:
        print(f'{label}: no common update ids (a={len(first[a])} b={len(first[b])})')
        return
    delta = sorted((first[b][u] - first[a][u]) / 1000 for u in common)
    pct = lambda p: delta[min(len(delta) - 1, int(p * len(delta)))]
    wins = sum(d > 0 for d in delta)
    print(f'{label}: n={len(delta)} {a}_first={wins} ({100 * wins / len(delta):.1f}%) {b}_first={sum(d < 0 for d in delta)}')
    print(f'   lead of {a} in us: mean={statistics.mean(delta):.0f} p10={pct(.1):.0f} p50={pct(.5):.0f} '
          f'p90={pct(.9):.0f} p99={pct(.99):.0f} min={delta[0]:.0f} max={delta[-1]:.0f}')


async def main():
    key = api_key()
    if key:
        FEEDS['sbe'] = (f'wss://stream-sbe.binance.com:9443/ws/{SYM}@bestBidAsk', decode_sbe, {'X-MBX-APIKEY': key})
    else:
        print(f'BINANCE_SBE_API_KEY is empty in environment and {ENV_FILE}; SBE skipped')
    stop = asyncio.Event()
    tasks = [asyncio.create_task(run(name, *feed, stop)) for name, feed in FEEDS.items() for _ in range(CONNS)]
    print(f'racing {DUR:.0f}s {SYM} feeds={list(FEEDS)} conns_per_feed={CONNS}', flush=True)
    await asyncio.sleep(DUR)
    stop.set()
    await asyncio.gather(*tasks, return_exceptions=True)
    for error in errors:
        print('connection error:', error)
    print('messages:', counts, 'unique ids:', {name: len(ids) for name, ids in first.items()})
    for a, b in itertools.combinations([name for name in ('sbe', 'stream', 'vision') if name in FEEDS], 2):
        summary(f'{a} vs {b}', a, b)
    if event_lag_us:
        lag = sorted(event_lag_us)
        print(f'sbe eventTime -> local wall clock, us (includes local clock offset): '
              f'p10={lag[len(lag) // 10]:.0f} p50={lag[len(lag) // 2]:.0f} p90={lag[len(lag) * 9 // 10]:.0f}')


asyncio.run(main())
