"""Fixed-token baseline adapter for the Decimal research policy; no IO.
Limits are per ticker across all routes, never independently per pool.
"""
from dataclasses import replace
from decimal import Decimal as D, ROUND_FLOOR
from metric_strategy import quantities,decide

def policy_at_baseline(policy,baseline,ask):
    return replace(policy,max_position_usdg=policy.max_position_usdg+baseline*ask)

def sizes(policy,inventory,baseline,ask,decimals=18):
    unit=D(10)**-decimals
    cash=max(D(0),inventory.cash-policy.gas)
    affordable=(cash/ask).quantize(unit,rounding=ROUND_FLOOR)
    if inventory.base<baseline:return {'buy':min(baseline-inventory.base,affordable),'sell':D(0)}
    if inventory.base>baseline:return {'buy':D(0),'sell':inventory.base-baseline}
    return {'buy':min(affordable,(policy.max_position_usdg/ask).quantize(unit,rounding=ROUND_FLOOR)),'sell':inventory.base}

def best_pool(policy,inventory,baseline,bbo,now,quotes,open_bps,close_bps):
    """One winning route for one shared ticker inventory. Quotes contain pool/side/quantity/quote.
    Caller must validate token identity before grouping pools. Never net unrelated wrappers.
    """
    ask=D(bbo['ask'])*policy.fx;cap=policy_at_baseline(policy,baseline,ask);candidates=[]
    for r in quotes:
        side=r['side'];q=D(r['quantity']);closing=inventory.base!=baseline
        if closing and ((inventory.base<baseline and side!='buy') or (inventory.base>baseline and side!='sell')):continue
        if closing and q>abs(inventory.base-baseline):continue
        v=decide(cap,inventory,side,q,r['quote'],bbo,now,threshold_override=close_bps if closing else open_bps)
        if v:candidates.append(dict(v,pool=r['pool'],phase='close' if closing else 'open'))
    return max(candidates,key=lambda r:(D(r['edge_bps']),r['pool'])) if candidates else None
