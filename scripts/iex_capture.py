"""Alpaca IEX push recorder. No trading APIs; RLLBIN + zstd, read by tape.py."""
import argparse
import asyncio
import collections
import datetime
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
from websockets.asyncio.client import connect
from tape import MAGIC, write_record


def credentials(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('\"\'')
    keys = ('APCA_API_KEY_ID', 'APCA_API_SECRET_KEY')
    if not all(values.get(k) for k in keys):
        raise ValueError('Missing Alpaca credential fields')
    return dict(action='auth', key=values[keys[0]], secret=values[keys[1]])


def exchange_ns(stamp):
    # Preserve all nine fractional digits, without float timestamp rounding.
    base, fraction = stamp.rstrip('Z').split('.') if '.' in stamp else (stamp.rstrip('Z'), '')
    dt = datetime.datetime.strptime(base, '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp()) * 1_000_000_000 + int(fraction.ljust(9, '0'))


async def capture(config, auth, directory, seconds):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    start = time.monotonic()
    status = dict(pid=os.getpid(), feed=config['feed'], endpoint=config['url'],
                  requested_symbols=config['symbols'], subscribed_symbols=[],
                  authenticated=False, connected=False, epoch=0, reconnects=0,
                  counts={}, last_quote_recv_ns={}, last_message_recv_ns=None,
                  started_ns=time.time_ns(), finished=False, error=None,
                  timestamp_semantics='recv_ns: Ohio application receipt before JSON decode; exchange_ns: vendor quote timestamp',
                  size_units='round_lots', quote_scope='IEX venue, not NBBO')
    counts = collections.Counter()
    with open(directory/'events.bin.zst', 'xb') as output:
        compressor = subprocess.Popen(['zstd', '-q', '-T1', '-c'], stdin=subprocess.PIPE, stdout=output)
        stream = compressor.stdin
        stream.write(MAGIC)
        def emit(kind, **fields):
            write_record(stream, dict(kind=kind, recv_ns=time.time_ns(), mono_ns=time.monotonic_ns(), epoch=status['epoch'], **fields))
        def save():
            status['counts'] = dict(counts)
            status['updated_ns'] = time.time_ns()
            status['symbols_without_quotes'] = sorted(set(config['symbols']) - set(status['last_quote_recv_ns']))
            tmp = directory/'status.tmp'
            tmp.write_text(json.dumps(status, indent=2)+'\n')
            tmp.replace(directory/'status.json')
            stream.flush()
        emit('iex_session', config=config, size_units='round_lots')
        delay = 1
        try:
            while not stop.is_set() and time.monotonic()-start < seconds:
                status['epoch'] += 1
                status.update(authenticated=False, connected=False, subscribed_symbols=[])
                handshake_deadline = time.monotonic() + 20
                try:
                    async with connect(config['url'], compression=None, open_timeout=10,
                                       ping_interval=20, ping_timeout=20, max_queue=16) as ws:
                        status['connected'] = True
                        emit('iex_connected')
                        await ws.send(json.dumps(auth))
                        last_save = 0
                        while not stop.is_set() and time.monotonic()-start < seconds:
                            now = time.monotonic()
                            if now-last_save >= 5:
                                if shutil.disk_usage(directory).free < config['disk_reserve_gib']*1024**3:
                                    raise OSError('disk_reserve_reached')
                                save()
                                last_save = now
                            if not status['subscribed_symbols'] and now > handshake_deadline:
                                raise TimeoutError('subscription_timeout')
                            try:
                                raw = await asyncio.wait_for(ws.recv(), timeout=1)
                            except asyncio.TimeoutError:
                                continue
                            recv_ns, mono_ns = time.time_ns(), time.monotonic_ns()
                            status['last_message_recv_ns'] = recv_ns
                            rows = json.loads(raw)
                            for row in rows:
                                kind = row.get('T')
                                if kind == 'q':
                                    symbol = row['S']
                                    if symbol not in config['symbols']:
                                        raise ValueError('unexpected_quote_symbol')
                                    write_record(stream, dict(kind='iex_bbo', symbol=symbol,
                                        recv_ns=recv_ns, mono_ns=mono_ns, epoch=status['epoch'],
                                        exchange_ns=exchange_ns(row['t']), bid=row['bp'], ask=row['ap'],
                                        bid_qty_lots=row['bs'], ask_qty_lots=row['as'],
                                        bid_exchange=row['bx'], ask_exchange=row['ax'],
                                        conditions=row.get('c', []), tape=row.get('z'), source_timestamp=row['t']))
                                    counts[symbol] += 1
                                    status['last_quote_recv_ns'][symbol] = recv_ns
                                elif kind == 'success':
                                    if row.get('msg') == 'authenticated':
                                        status['authenticated'] = True
                                        await ws.send(json.dumps(dict(action='subscribe', quotes=config['symbols'])))
                                        emit('iex_authenticated')
                                elif kind == 'subscription':
                                    subscribed = sorted(row.get('quotes', []))
                                    emit('iex_subscription', symbols=subscribed)
                                    if set(subscribed) != set(config['symbols']):
                                        raise ValueError('subscription_mismatch')
                                    status['subscribed_symbols'] = subscribed
                                    status['error'] = None
                                    delay = 1
                                    save()
                                elif kind == 'error':
                                    # Never log arbitrary server messages or authentication frames.
                                    code = row.get('code')
                                    emit('iex_api_error', code=code)
                                    raise ConnectionError('alpaca_error_'+str(code))
                except (OSError, ValueError, ConnectionError, TimeoutError) as exc:
                    # Only our fixed identifiers are exported, never request headers/secrets.
                    label = str(exc) if str(exc).startswith(('alpaca_error_', 'disk_reserve_', 'subscription_', 'unexpected_quote_')) else type(exc).__name__
                    status['error'] = label
                    if label == 'disk_reserve_reached':
                        raise
                except Exception as exc:
                    status['error'] = type(exc).__name__
                finally:
                    status.update(connected=False, authenticated=False, subscribed_symbols=[])
                    emit('iex_gap', reason=status['error'] or 'connection_closed')
                    save()
                if not stop.is_set() and time.monotonic()-start < seconds:
                    status['reconnects'] += 1
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=delay)
                    except asyncio.TimeoutError:
                        pass
                    delay = min(delay*2, 60)
        finally:
            status['finished'] = True
            emit('iex_stopped')
            save()
            stream.close()
            if compressor.wait(timeout=30) != 0:
                raise RuntimeError('binary_compression_failed')
    return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config/iex-ohio.json')
    parser.add_argument('--credentials', required=True)
    parser.add_argument('--directory')
    parser.add_argument('--seconds', type=int, default=86400)
    args = parser.parse_args()
    config = json.load(open(args.config))
    if len(config['symbols']) != len(set(config['symbols'])) or not config['symbols']:
        raise ValueError('invalid symbol catalog')
    if shutil.disk_usage('.').free < config['disk_reserve_gib']*1024**3:
        raise RuntimeError('disk_reserve_reached')
    auth = credentials(args.credentials)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    directory = args.directory or 'captures/ohio-iex-'+stamp
    asyncio.run(capture(config, auth, directory, args.seconds))


if __name__ == '__main__':
    main()
