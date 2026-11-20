"""Observed parent single-sell value check; not full root validity."""

def sell_value_gate(weth_spent,usdg_received,oracle_answer,slot0):
    """Raw WETH18/USDG6, positive oracle8 answer, packed parent slot0.

    Caller must establish the positive-answer oracle branch and single-sell
    inventory path. Buys/mixed routes, fallback prices and oracle updates remain
    outside this arithmetic helper.
    """
    if any(type(x) is not int or not 0<=x<1<<256 for x in (weth_spent,usdg_received,oracle_answer,slot0)):
        raise ValueError('value gate input bounds')
    if not weth_spent or not oracle_answer:raise ValueError('positive sell/oracle required')
    bps=(slot0>>176)&65535
    if bps>1000:raise ValueError('unverified tolerance setting')
    marked=weth_spent*oracle_answer//10**20
    if marked>=1<<255:raise ValueError('signed valuation bounds')
    delta=usdg_received-marked;allowance=marked*bps//10000+10
    if not -(1<<255)<=delta<1<<255:raise ValueError('signed delta bounds')
    return dict(marked=marked,delta=delta,tolerance=allowance,passes=delta>=-allowance)
