"""Research mode40/index4 intent and local route transition, no I/O.

Caller must supply state/inventory AFTER all upstream routes. This does not
select economic branches or validate final router settlement/oracle checks.
"""
from routera3d_price import route_fields,mode40_limit_fee_hint,block_window,reverse_v3_limit,forward_v3_limit
from index4_fee import integer
from index4_local import POOL
WETH='0x0bd7d308f8e1639fab988df18a8011f41eacad73'
USDG='0x5fc5360d0400a0fd4f2af552add042d716f1d168'

def intent(calldata,position,inventory):
    plan=route_fields(calldata)
    integer(position,0,len(plan['routes'])-1,'route position')
    route=plan['routes'][position]
    if plan['mode']!=0x40 or route['index']!=4 or route['flags']!=9 or route['adjustment']>=0:
        raise ValueError('unverified index4 route branch')
    hint=mode40_limit_fee_hint(calldata)
    if hint['fallback_required']:raise ValueError('index4 zero hint requires verified getter fallback')
    for token in (WETH,USDG):integer(inventory[token],0,(1<<256)-1,'router inventory')
    zero=route['side']==2;discount=-route['adjustment']
    adjusted=plan['price']*(100000-discount)//100000
    if not adjusted:raise ValueError('zero adjusted price')
    cap=plan['cap']*10**18//adjusted if zero else plan['cap']
    amount=min(inventory[WETH if zero else USDG],cap)
    integer(amount,1,(1<<127)-1,'supported route input')
    limit=(forward_v3_limit if zero else reverse_v3_limit)(plan['price'],discount,hint['limit_fee_hint_ppm'],10)
    return dict(pool=POOL,zero=zero,amount=amount,limit=limit,limit_fee_hint_ppm=hint['limit_fee_hint_ppm'])

def preview(pool_state,calldata,position,inventory,*,block,timestamp,router_slot9):
    if not block_window(calldata,block,router_slot9)['valid']:raise ValueError('router calldata outside block window')
    route=intent(calldata,position,inventory)
    transition=pool_state.preview_exact_input(block=block,timestamp=timestamp,zero=route['zero'],amount=route['amount'],limit=route['limit'])
    balances=dict(inventory)
    balances[WETH]-=transition['result']['amount0'];balances[USDG]-=transition['result']['amount1']
    for value in (balances[WETH],balances[USDG]):integer(value,0,(1<<256)-1,'post-route inventory')
    return dict(**transition,intent=route,inventory=balances,inventory_phase='before_unmodeled_final_settlement')
