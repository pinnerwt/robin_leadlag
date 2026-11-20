"""Streaming reader for RLLBIN v1, including positional Binance records."""
import contextlib
import json
from pathlib import Path
import struct
import subprocess

MAGIC=b'RLLBIN\x01\n'
LIVE='symbol update_id tokyo_recv_ns bid ask bid_qty ask_qty ws_link relay_seq ohio_recv_ns relay_link'.split()
PROBE='ms bid ask symbol update_id bid_qty ask_qty mono_ns recv_ns link epoch'.split()
MAX_FRAME=8*1024*1024

def exact(stream,n):
    data=stream.read(n)
    if len(data)!=n:raise ValueError('truncated binary journal')
    return data

def decode(data):
    pos=0
    def take(n):
        nonlocal pos
        if n<0 or pos+n>len(data):raise ValueError('truncated value')
        result=data[pos:pos+n];pos+=n;return result
    def integer():return struct.unpack('<I',take(4))[0]
    def string():return take(integer()).decode('utf8')
    def value(depth=0):
        if depth>=64:raise ValueError('excessive nesting')
        tag=take(1)[0]
        if tag<3:return [None,False,True][tag]
        if tag in (3,4,5):return struct.unpack({3:'<Q',4:'<q',5:'<d'}[tag],take(8))[0]
        if tag==6:return string()
        if tag in (7,8):
            n=integer()
            if n>len(data)-pos:raise ValueError('invalid collection length')
            if tag==7:return [value(depth+1) for _ in range(n)]
            return {string():value(depth+1) for _ in range(n)}
        if tag in (9,10):
            keys=LIVE if tag==9 else PROBE
            mask=struct.unpack('<H',take(2))[0]
            if mask>>len(keys):raise ValueError('unknown positional field')
            row={'kind':'binance_bbo' if tag==9 else 'bbo'}
            for i,key in enumerate(keys):
                if mask & (1<<i):row[key]=value(depth+1)
            return row
        raise ValueError(f'unknown type {tag}')
    result=value()
    if pos!=len(data):raise ValueError('trailing bytes')
    return result

def read(stream):
    if exact(stream,8)!=MAGIC:raise ValueError('unknown journal version')
    while first:=stream.read(1):
        size=struct.unpack('<I',first+exact(stream,3))[0]
        if not 0<size<=MAX_FRAME:raise ValueError('invalid frame size')
        yield decode(exact(stream,size))

@contextlib.contextmanager
def open_tape(path):
    if str(path)=='-':
        import sys
        yield sys.stdin.buffer
        return
    path=Path(path)
    if path.suffix=='.zst':
        process=subprocess.Popen(['zstd','-q','-dc','--',str(path)],stdout=subprocess.PIPE)
        try:
            yield process.stdout
        finally:
            process.stdout.close()
            status=process.wait()
            if status:raise ValueError(f'zstd failed: {status}')
    else:
        with path.open('rb') as stream:yield stream

def records(paths):
    for path in paths:
        with open_tape(path) as stream:yield from read(stream)

if __name__=='__main__':
    import sys
    for row in records(sys.argv[1:]):print(json.dumps(row,separators=(',',':')))


def encode(value):
    """Encode the existing RLLBIN generic value format (large ints as strings)."""
    def string(text):
        raw = text.encode('utf8')
        return struct.pack('<I', len(raw)) + raw
    if value is None:return b'\x00'
    if value is False:return b'\x01'
    if value is True:return b'\x02'
    if isinstance(value, int):
        if 0 <= value < 1 << 64:return b'\x03' + struct.pack('<Q', value)
        if -(1 << 63) <= value < 0:return b'\x04' + struct.pack('<q', value)
        return b'\x06' + string(str(value))
    if isinstance(value, float):return b'\x05' + struct.pack('<d', value)
    if isinstance(value, str):return b'\x06' + string(value)
    if isinstance(value, (list, tuple)):
        return b'\x07' + struct.pack('<I', len(value)) + b''.join(encode(v) for v in value)
    if isinstance(value, dict):
        return b'\x08' + struct.pack('<I', len(value)) + b''.join(string(str(k)) + encode(v) for k, v in value.items())
    raise TypeError(type(value).__name__)


def write_record(stream, row):
    raw = encode(row)
    if not 0 < len(raw) <= MAX_FRAME:raise ValueError('invalid frame size')
    stream.write(struct.pack('<I', len(raw)) + raw)
