"""Observed index-6 reverse route arithmetic; no RPC or logs.

Caller must separately establish the active hook fee and branch. This does not
model hook updates, economic gating or final transaction settlement.
"""
from routera3d_price import route_fields,reverse_v3_limit
WETH='0x0bd7d308f8e1639fab988df18a8011f41eacad73'
USDG='0x5fc5360d0400a0fd4f2af552add042d716f1d168'
MANAGER='0x8366a39cc670b4001a1121b8f6a443a643e40951'
HOOK='0x987e330f00b79864a07fe81dfac344d0078abcc0'
NATIVE='0x'+'00'*20
POOL_ID='0xa791e5169faf703c0b63fd9552c33ec1128a773a00f5dc33a640da62a022cd35'


def reverse_intent(calldata,route_index,usdg_inventory,*,hook_fee_ppm):
    plan=route_fields(calldata)
    if type(route_index) is not int or not 0<=route_index<len(plan['routes']):
        raise ValueError('route position')
    route=plan['routes'][route_index]
    if plan['mode']!=0xe0 or route['index']!=6 or route['flags']!=9 or route['side']!=1 or route['adjustment']>=0:
        raise ValueError('unverified V4 route branch')
    if type(usdg_inventory) is not int or not 0<=usdg_inventory<1<<256:
        raise ValueError('inventory bounds')
    if type(hook_fee_ppm) is not int or hook_fee_ppm!=40:
        raise ValueError('unverified hook fee branch')
    amount=min(usdg_inventory,plan['cap'])
    if not 0<amount<1<<127:raise ValueError('unverified amount range')
    return dict(manager=MANAGER,currency0=NATIVE,currency1=USDG,fee=0x800000,
                tick_spacing=1,hooks=HOOK,zero=False,amount=-amount,
                limit=reverse_v3_limit(plan['price'],-route['adjustment'],hook_fee_ppm,10),
                state_complete=False)


def settled_inventory(inventory,delta0,delta1):
    """Apply successful reverse V4 caller deltas after native wrapping/delivery.

    Deltas must come from local execution/state math, never future event logs.
    This pure helper does not assume that attempted swap frames committed.
    """
    if any(type(x) is not int or not -(1<<127)<=x<1<<127 for x in (delta0,delta1)):
        raise ValueError('V4 int128 deltas')
    if delta0<=0 or delta1>=0:raise ValueError('unverified settlement direction')
    result=dict(inventory)
    for token in (WETH,USDG):
        if token not in result or type(result[token]) is not int or not 0<=result[token]<1<<256:
            raise ValueError('missing or invalid inventory')
    result[WETH]+=delta0;result[USDG]+=delta1
    if any(not 0<=result[t]<1<<256 for t in (WETH,USDG)):
        raise ValueError('settled inventory bounds')
    return result


def forward_intent(calldata,route_index,weth_inventory,*,hook_fee_ppm):
    """Observed index-6 sell sizing; settlement is separately unverified."""
    from routera3d_price import forward_v3_limit
    plan=route_fields(calldata)
    if type(route_index) is not int or not 0<=route_index<len(plan['routes']):raise ValueError('route position')
    route=plan['routes'][route_index]
    if plan['mode']!=0xe0 or route['index']!=6 or route['flags']!=9 or route['side']!=2 or route['adjustment']>=0:
        raise ValueError('unverified V4 sell branch')
    if type(weth_inventory) is not int or not 0<=weth_inventory<1<<256:raise ValueError('inventory bounds')
    if type(hook_fee_ppm) is not int or hook_fee_ppm!=160:raise ValueError('unverified sell hook fee')
    adjusted=plan['price']*(100000+route['adjustment'])//100000
    if not adjusted:raise ValueError('zero adjusted price')
    amount=min(weth_inventory,plan['cap']*10**18//adjusted)
    if not 0<amount<1<<127:raise ValueError('unverified amount range')
    return dict(manager=MANAGER,currency0=NATIVE,currency1=USDG,fee=0x800000,tick_spacing=1,
                hooks=HOOK,zero=True,amount=-amount,
                limit=forward_v3_limit(plan['price'],-route['adjustment'],hook_fee_ppm,10),state_complete=False)


def dynamic_intent(calldata,route_index,inventory,*,hook_state,hook_config,sqrt,block):
    """Default-profile local hook fee plus verified index-6 router arithmetic."""
    from routera3d_hook import reverse_update,forward_update
    from routera3d_price import forward_v3_limit
    plan=route_fields(calldata)
    if type(route_index) is not int or not 0<=route_index<len(plan['routes']):raise ValueError('route position')
    route=plan['routes'][route_index];zero=route['side']==2
    change=(forward_update if zero else reverse_update)(hook_state,hook_config,sqrt,block)
    # Sizing/envelope validation is independent of fee; replace the bound using
    # the verified hook branch instead of trusting an arbitrary caller fee.
    intent=(forward_intent if zero else reverse_intent)(calldata,route_index,inventory,hook_fee_ppm=160 if zero else 40)
    intent['limit']=(forward_v3_limit if zero else reverse_v3_limit)(plan['price'],-route['adjustment'],change['fee'],10)
    return dict(intent,hook_fee_ppm=change['fee'],hook_state_after=change['after'])
