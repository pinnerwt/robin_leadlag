"""Verified cc1a two-token 2 -> 13 route plan, success-assumption research.

Not registered with the live reducer: other route opcodes, guard modes and
settlement behavior remain unsupported. Amount expressions bind to local swap
results, never to calldata reference-price fields or executed logs.
"""
from inspect_cc1a import inspect, ADDRESS

V3_POOL='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca'
USDG='0x5fc5360d0400a0fd4f2af552add042d716f1d168'
WETH='0x0bd7d308f8e1639fab988df18a8011f41eacad73'


def plan(data):
    raw=bytes.fromhex(data.removeprefix('0x'))
    frame=inspect(data)
    if raw[4:12] != bytes.fromhex('0000000000034402'):
        raise ValueError('cc1a header mode not verified')
    if frame['tokens'] != [USDG,WETH]:
        raise ValueError('cc1a token path not verified')
    first,second=frame['records']
    if first['opcode']!=2 or second['opcode']!=13:
        raise ValueError('cc1a route opcode path not verified')
    body=bytes.fromhex(second['body'])
    if len(body)!=22 or body[-1]!=1:
        raise ValueError('cc1a Metric direction mode not verified')
    amount=frame['initial_amount']
    if amount<=0:raise ValueError('nonpositive initial input')
    return [dict(venue='uniswap_v3',pool=V3_POOL,zero=False,amount=amount,
                 limit=1461446703485210103287273052203988822378723970341),
            dict(venue='metric',pool='0x'+body[1:21].hex(),zero=True,
                 amount_from=dict(step=0,field='amount0',negate=True),
                 sender=ADDRESS,recipient=ADDRESS,min_output=0)]


def bind_output(operation,results):
    """Resolve a dependent exact input only after its producer was simulated."""
    source=operation['amount_from']
    index=source['step']
    if index<0 or index>=len(results):raise ValueError('missing upstream result')
    result=results[index]
    if result.get('unfilled',0):raise ValueError('partial upstream fill not verified')
    amount=int(result[source['field']])*(-1 if source['negate'] else 1)
    if amount<=0:raise ValueError('nonpositive upstream output')
    return amount
