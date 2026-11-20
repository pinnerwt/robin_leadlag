"""Verified fixed-amount parallel V3 routes. No RPC or log-derived arguments."""
from v3_calldata import word, blob, address
from v3_state import MIN_SQRT, MAX_SQRT

ROUTER_426='0x4262efbd176f02824af27010bea218429c33c7e8'
AGGREGATOR='0x006102b16a04c20306a28b652745d3973d7d24fa'
ADAPTER='0x7e0aab35a05e63381e7e89f34cbb9df1f5f1baa9'


def decode_426(raw, profile, pools):
    if profile.get('profile')!='426-parallel-v3-v1' or not profile.get('implementation_code_hash'):
        raise ValueError('unversioned 426 proxy profile')
    if pools is None:raise ValueError('426 requires tracked pool metadata')
    if raw[:4].hex()!='32038e4b':raise ValueError('426 outer selector not verified')
    d=raw[4:]
    if address(word(d,1))!=AGGREGATOR:raise ValueError('426 aggregator not verified')
    if word(d,8)!=0 or word(d,9)!=0 or word(d,11)!=416:
        raise ValueError('426 outer mode not verified')
    inner=blob(d,word(d,11))
    if inner[:4].hex()!='b86f0777':raise ValueError('426 inner selector not verified')
    body=inner[4:]
    if word(body,5)!=0 or word(body,8)!=288:raise ValueError('426 aggregator mode not verified')
    tokenin,tokenout=address(word(body,1)),address(word(body,2))
    if tokenin!=address(word(d,2)) or tokenout!=address(word(d,3)):
        raise ValueError('426 token forwarding mismatch')
    total=word(body,3)
    if not 0<total<(1<<255) or total!=word(d,4) or total!=word(d,5):
        raise ValueError('426 dynamic or modified input amount')
    offset=word(body,8);count=word(body[offset:],0);base=offset+32
    if not 0<count<=64:raise ValueError('426 route count')
    result=[];allocated=0
    for i in range(count):
        relative=word(body[base:],i)
        if relative<count*32 or relative%32:raise ValueError('426 route tuple offset')
        route=body[base+relative:]
        if address(word(route,0))!=ADAPTER:raise ValueError('426 adapter not verified')
        if address(word(route,1))!=tokenin or address(word(route,3))!=tokenout:
            raise ValueError('426 dependent or multihop route not supported')
        amount=word(route,2)
        if not 0<amount<(1<<255):raise ValueError('426 dynamic route amount')
        allocated+=amount
        if word(route,5)!=192:raise ValueError('426 adapter data offset')
        data=blob(route,192)
        if len(data)!=64 or word(data,0)!=3:raise ValueError('426 non-V3 adapter branch')
        fee=word(data,1)
        if not 0<fee<1000000:raise ValueError('426 invalid fee')
        found=[a for a,p in pools.items() if p['fee']==fee and set(p['tokens'])=={tokenin,tokenout}]
        if len(found)>1:raise ValueError('ambiguous tracked pool')
        if not found:continue
        pool=found[0];zero=tokenin==pools[pool]['tokens'][0]
        result.append(dict(kind='swap',pool=pool,zero=zero,amount=amount,
            limit=MIN_SQRT+1 if zero else MAX_SQRT-1,constraint=None,
            decoder='426-parallel-v3-v1',source_route_index=i))
    if allocated!=total:raise ValueError('426 route allocations do not equal fixed input')
    return result
