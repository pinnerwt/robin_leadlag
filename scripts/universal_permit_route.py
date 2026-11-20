"""Verified 204f Universal Router Permit2 + single V3 exact-output path."""
from v3_calldata import word,blob,array,address,path
ROUTER='0x204faca1764b154221e35c0d20abb3c525710498'

def decode(raw,pools):
    if raw[:4].hex()!='3593564c':raise ValueError('Universal execute selector')
    d=raw[4:]
    commands=blob(d,word(d,0));inputs=array(d,word(d,1))
    if commands==b'\x00\x0c\x04' and len(inputs)==3:
        return decode_input_unwrap(inputs,pools)
    if commands!=b'\x0a\x01' or len(inputs)!=2:raise ValueError('Universal command sequence not verified')
    permit,swap=inputs
    if len(permit)!=352 or word(permit,6)!=224 or len(blob(permit,224))!=65:
        raise ValueError('Permit2 layout')
    token=address(word(permit,0))
    if word(permit,1)>=1<<160 or word(permit,2)>=1<<48 or word(permit,3)>=1<<48:
        raise ValueError('Permit2 integer width')
    if address(word(permit,4))!=ROUTER:raise ValueError('Permit2 spender')
    if len(swap)!=320 or word(swap,3)!=192 or word(swap,4)!=1 or word(swap,5)!=288 or blob(swap,288):
        raise ValueError('Universal swap callback or payer mode')
    address(word(swap,0))
    hops=path(blob(swap,192))
    if len(hops)!=1:raise ValueError('Universal multihop unverified')
    out,inp,fee=hops[0]
    if token!=inp:raise ValueError('Permit2 input mismatch')
    amount=word(swap,1)
    if not 0<amount<1<<255:raise ValueError('Universal output amount')
    matches=[a for a,p in pools.items() if p['fee']==fee and set(p['tokens'])=={inp,out}]
    if not matches:return []
    if len(matches)!=1:raise ValueError('ambiguous Universal pool')
    pool=matches[0]
    return [dict(kind='swap',pool=pool,zero=inp==pools[pool]['tokens'][0],amount=-amount,
                 limit=None,constraint=dict(kind='max_in',amount=word(swap,2)),decoder='204f-permit-v3-v1')]


def decode_input_unwrap(inputs,pools):
    swap,unwrap,sweep=inputs
    if len(swap)!=320 or word(swap,0)!=2 or word(swap,3)!=192 or word(swap,4)!=1 or word(swap,5)!=288 or blob(swap,288):
        raise ValueError('Universal exact-input mode')
    if len(unwrap)!=64 or len(sweep)!=96 or word(sweep,0)!=0 or word(sweep,2)!=0:
        raise ValueError('Universal native settlement layout')
    if address(word(unwrap,0))!=address(word(sweep,1)):raise ValueError('Universal settlement recipient mismatch')
    hops=path(blob(swap,192))
    if len(hops)!=1:raise ValueError('Universal multihop unverified')
    inp,out,fee=hops[0]
    if out!='0x0bd7d308f8e1639fab988df18a8011f41eacad73':raise ValueError('Universal unwrap requires WETH')
    amount=word(swap,1)
    if not 0<amount<1<<255:raise ValueError('Universal dynamic input unsupported')
    matches=[a for a,p in pools.items() if p['fee']==fee and set(p['tokens'])=={inp,out}]
    if not matches:return []
    if len(matches)!=1:raise ValueError('ambiguous Universal pool')
    pool=matches[0]
    return [dict(kind='swap',pool=pool,zero=inp==pools[pool]['tokens'][0],amount=amount,
                 limit=None,constraint=dict(kind='min_out',amount=word(swap,2)),decoder='204f-permit-v3-v1',
                 coverage_note='swap decoded; native settlement recipient execution not modeled')]
