"""c9 bad401db callback extraction. Upstream settlement remains unresolved."""
from v3_calldata import word,address,blob,decode
C9='0xc9a1dcff54632b408f2b0e048d8b7d3261697144'
AGGREGATOR='0x111111338c5091e8440b67b168bae16a668ac0de'
V3_ROUTER='0xcaf681a66d020601342297493863e78c959e5cb2'

def one_call(data,offset):
    if word(data[offset:],0)!=1 or word(data[offset+32:],0)!=32:
        raise ValueError('c9 requires exactly one call per array')
    start=offset+64;body=data[start:]
    if word(body,1)!=128:raise ValueError('c9 call tuple layout')
    payload=blob(body,128)
    end=start+160+((len(payload)+31)//32)*32
    if end>len(data):raise ValueError('c9 truncated tuple padding')
    return address(word(body,0)),payload,word(body,2),word(body,3),end

def decode_c9(raw,pools):
    if raw[:4].hex()!='bad401db':raise ValueError('c9 selector not verified')
    d=raw[4:]
    if word(d,4)!=224:raise ValueError('c9 primary array offset')
    target,payload,approval,allowance,end=one_call(d,224)
    if target!=AGGREGATOR or address(word(d,0))!=AGGREGATOR or approval or allowance:
        raise ValueError('c9 primary route not verified')
    if payload[:4].hex()!='f4d2d412':raise ValueError('c9 primary selector')
    inner=payload[4:]
    if word(inner,0)!=160 or word(inner,4)!=448:
        raise ValueError('c9 aggregator tuple layout')
    if word(inner,1)!=word(d,1) or word(inner,2)!=word(d,3) or word(inner,3)!=word(d,2):
        raise ValueError('c9 primary token/amount mismatch')
    if word(d,5)!=end:raise ValueError('c9 callback array offset')
    target,callback,approval,allowance,end=one_call(d,end)
    if end!=len(d) or target!=V3_ROUTER or callback[:4].hex()!='5023b4df' or len(callback)!=228:
        raise ValueError('c9 callback path not verified')
    c=callback[4:]
    if approval!=word(d,3) or allowance!=(1<<256)-1:
        raise ValueError('c9 callback approval mode')
    if word(c,0)!=word(d,3) or word(c,1)!=word(d,1) or word(c,4)!=word(d,2) or address(word(c,3))!=C9:
        raise ValueError('c9 exact-output callback mismatch')
    operations=decode(target,'0x'+callback.hex(),pools,{V3_ROUTER})
    if not operations:raise ValueError('c9 unrecorded callback does not resolve opaque primary route')
    for op in operations:
        op['decoder']='c9-callback-v1'
        op['coverage_note']='exact-output callback decoded; upstream aggregator settlement not executed'
    return operations
