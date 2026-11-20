"""Initialization adapter for verified zero-fee and 40-ppm override V4 branches.

Hashing is initialization-only. Runtime swaps use integer State arithmetic.
Requires a separately verified zero-delta hook branch; not a generic V4 model.
"""
from bootstrap_state import hashhex,word,mapping
from v3_state import State

def signed(n,bits):return n-(1<<bits) if n>>(bits-1) else n

def load(storage,key,*,effective_lp_fee=None,bitmap_words=None):
    if key['fee']==0 and effective_lp_fee is None:
        fee=0
    elif key['fee']==0x800000 and type(effective_lp_fee) is int and effective_lp_fee==40:
        fee=effective_lp_fee
    else:raise ValueError('unverified V4 fee branch')
    if type(key['tick_spacing']) is not int or not 0<key['tick_spacing']<1<<23:
        raise ValueError('V4 tick spacing')
    raw={int(k,16):int(v,16) for k,v in storage.items()}
    pool_id=hashhex(b''.join(word(v) for v in [int(key['currency0'],16),int(key['currency1'],16),key['fee'],key['tick_spacing'],int(key['hooks'],16)]))
    base=int(mapping(int(pool_id,16),6),16)
    if base not in raw or base+3 not in raw:raise ValueError('missing V4 slot0/liquidity')
    slot0=raw[base];sqrt=slot0&((1<<160)-1);tick=signed((slot0>>160)&((1<<24)-1),24)
    if slot0>>184:raise ValueError('nonzero V4 protocol/LP fees or reserved bits')
    liquidity=raw[base+3]
    if liquidity>=1<<128:raise ValueError('V4 liquidity width')
    spacing=key['tick_spacing'];bitmap={};ticks={}
    lower=(-887272//spacing)>>8;upper=(887272//spacing)>>8
    words=range(lower,upper+1) if bitmap_words is None else list(bitmap_words)
    if any(type(i) is not int or not lower<=i<=upper for i in words):
        raise ValueError('bitmap word bounds')
    for index in words:
        slot=int(mapping(index,base+5),16)
        if slot not in raw:continue # Unknown words remain unavailable, never zero-filled.
        bitmap[index]=raw[slot]
        for bit in range(256):
            if not raw[slot]&(1<<bit):continue
            tick_index=(index*256+bit)*spacing
            tick_slot=int(mapping(tick_index,base+4),16)
            if tick_slot in raw:
                value=raw[tick_slot];ticks[tick_index]=(value&((1<<128)-1),signed(value>>128,128))
    return State(sqrt,tick,liquidity,fee,spacing,bitmap,ticks)
