"""Strict C7 route plan. Resolve callback from local balance, never swap logs.

Research only: caller must maintain Aqua allocations and router token balances.
Not registered as complete coverage until both states are integrated atomically.
"""
from aqua_program import parse,quote_exact_input,checked
from c9_router import C9,AGGREGATOR,V3_ROUTER
from v3_calldata import word,address,blob,decode


def one_call(data,offset):
    if word(data[offset:],0)!=1 or word(data[offset+32:],0)!=32:
        raise ValueError('C7 requires one call per array')
    start=offset+64;body=data[start:]
    if word(body,1)!=224:raise ValueError('C7 tuple layout')
    payload=blob(body,224)
    end=start+256+((len(payload)+31)//32)*32
    if end>len(data):raise ValueError('C7 truncated padding')
    return [word(body,i) for i in range(7)],payload,end


def plan(calldata):
    raw=bytes.fromhex(calldata.removeprefix('0x')) if isinstance(calldata,str) else calldata
    if raw[:4].hex()!='c7e280dd':raise ValueError('C7 selector')
    d=raw[4:]
    if word(d,4)!=224 or address(word(d,0))!=AGGREGATOR:raise ValueError('C7 header')
    primary,payload,end=one_call(d,224)
    if address(primary[0])!=AGGREGATOR or any(primary[2:]):raise ValueError('C7 primary mode')
    if payload[:4].hex()!='f4d2d412':raise ValueError('C7 primary selector')
    inner=payload[4:]
    if word(inner,0)!=160 or word(inner,4)!=448:raise ValueError('C7 primary layout')
    tin,tout=address(word(inner,1)),address(word(inner,2))
    if word(inner,1)!=word(d,1) or word(inner,3)!=word(d,2) or word(d,3)!=word(d,1):
        raise ValueError('C7 input/output mismatch')
    desc=inner[160:]
    if word(desc,1)!=1<<254 or word(desc,2)!=96:raise ValueError('C7 maker traits')
    program=blob(desc,96);parse(program)
    # Exact observed taker mode; callbacks/other traits must not be silently accepted.
    taker=blob(inner,448)
    if len(inner)!=512 or taker!=bytes.fromhex('00000000000000000000000000000000000000000005'):
        raise ValueError('C7 taker mode')
    if word(d,5)!=end:raise ValueError('C7 callback offset')
    cb,callback,end=one_call(d,end)
    if end!=len(d) or address(cb[0])!=V3_ROUTER or callback[:4].hex()!='04e45aaf' or len(callback)!=228:
        raise ValueError('C7 callback shape')
    if cb[2:]!=[int(tout,16),0,int(tout,16),10000,132]:raise ValueError('C7 balance patch mode')
    c=callback[4:]
    if address(word(c,0))!=tout or address(word(c,1))!=tin or address(word(c,3))!=C9:
        raise ValueError('C7 callback tokens/recipient')
    if word(c,5) or word(c,6):raise ValueError('C7 callback constraints')
    return dict(maker=address(word(desc,0)),token_in=tin,token_out=tout,amount=word(inner,3),
                program=program.hex(),primary='0x'+payload.hex(),callback='0x'+callback.hex())


def resolve_callback(route,callback_balance,pools):
    """Balance at callback entry, including pre-existing inventory; no zero default."""
    checked(callback_balance)
    callback=bytearray.fromhex(route['callback'][2:])
    callback[132:164]=callback_balance.to_bytes(32,'big')
    return decode(V3_ROUTER,bytes(callback),pools,{V3_ROUTER})


def preview(calldata,balance_in,balance_out,router_balance_before,pools):
    """Aqua output plus known pre-existing router inventory funds the V3 swap.

    No state committed. Assumes standard token transfers and successful calls.
    Even an unrecorded callback leaves Aqua state relevant to later routes.
    """
    route=plan(calldata)
    checked(router_balance_before)
    quote=quote_exact_input(bytes.fromhex(route['program']),route['token_in'],route['token_out'],
                            balance_in,balance_out,route['amount'])
    if quote['amount_out']>balance_out or quote['protocol_fee']>balance_in:
        raise ValueError('Aqua allocation cannot fund withdrawals')
    amount=checked(router_balance_before+quote['amount_out'])
    return dict(route=route,quote=quote,callback_balance=amount,
                operations=resolve_callback(route,amount,pools),state_complete=False)


def allocation_transition(calldata,packed_in,packed_out,router_balance_before,pools):
    """Return candidate Aqua allocations and dependent V3 operation atomically.

    Caller must publish only after the dependent V3 transition also succeeds.
    Verified C7 callback pushes the full original input, not input minus LP fee.
    Does not update router inventory or execute V3; no mutation of supplied state.
    """
    from aqua_program import transition_exact_input
    route=plan(calldata)
    candidate=transition_exact_input(bytes.fromhex(route['program']),route['token_in'],route['token_out'],
                                     packed_in,packed_out,route['amount'])
    checked(router_balance_before)
    amount=checked(router_balance_before+candidate['quote']['amount_out'])
    return dict(candidate,route=route,callback_balance=amount,
                operations=resolve_callback(route,amount,pools),state_complete=False)
