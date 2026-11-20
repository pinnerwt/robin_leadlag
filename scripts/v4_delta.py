"""Decode PoolManager's signed int128 pair; research execution results only."""
def decode(data):
    raw=bytes.fromhex(data.removeprefix('0x')) if isinstance(data,str) else data
    if len(raw)!=32:raise ValueError('V4 BalanceDelta must be one word')
    value=int.from_bytes(raw,'big')
    def signed(n):return n-(1<<128) if n>>127 else n
    return signed(value>>128),signed(value&((1<<128)-1))
