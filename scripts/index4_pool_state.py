"""Index4 initialization adapter. Runtime swaps use in-memory State only.

Fee must come from the local dynamic-fee calculation for this transaction;
router limit hints are not charged fees. Unavailable words/ticks stay unknown.
"""
from bootstrap_state import mapping
from v3_state import State,MIN_TICK,MAX_TICK,MIN_SQRT,MAX_SQRT

def load(storage,*,effective_fee,bitmap_words):
    if type(effective_fee) is not int or not 0<=effective_fee<1000000:
        raise ValueError('explicit effective fee required')
    raw={int(k,16):int(v,16) for k,v in storage.items()}
    if any(k not in raw for k in (6,12,13)):raise ValueError('missing index4 core state')
    sqrt=raw[6]&((1<<160)-1);tick=raw[6]>>160&((1<<24)-1)
    if tick&(1<<23):tick-=1<<24
    spacing=raw[12]>>176&((1<<24)-1);liquidity=raw[13]&((1<<128)-1)
    if not MIN_SQRT<=sqrt<MAX_SQRT or not MIN_TICK<=tick<=MAX_TICK or not 0<spacing<1<<23:
        raise ValueError('invalid index4 curve state')
    bitmap={};ticks={}
    for index in bitmap_words:
        if type(index) is not int or not ((MIN_TICK//spacing)>>8)<=index<=((MAX_TICK//spacing)>>8):
            raise ValueError('bitmap word bounds')
        slot=int(mapping(index,15),16)
        if slot not in raw:continue
        bitmap[index]=raw[slot]
        for bit in range(256):
            if not raw[slot]>>bit&1:continue
            t=(index*256+bit)*spacing;key=int(mapping(t,14),16)
            if key not in raw:continue
            value=raw[key];gross=value&((1<<128)-1);net=value>>128
            if net&(1<<127):net-=1<<128
            if not gross or abs(net)>gross:raise ValueError('invalid initialized tick liquidity')
            ticks[t]=(gross,net)
    return State(sqrt,tick,liquidity,effective_fee,spacing,bitmap,ticks)
