"""Integer quote for one bytecode-validated Aqua SwapVM program shape.

Reference: 1inch/swap-vm v1.0.1 (363e3fea...), Fee.sol,
XYCConcentrate.sol and XYCSwap.sol. Newer banked opcode numbering is different.
Permission/funding checks are assumed successful; no settlement writes here.
"""
from math import isqrt
ONE=10**18
FEE_SCALE=10**9
MAX=(1<<256)-1

def checked(n):
    if not 0<=n<=MAX:raise ValueError('uint256 overflow')
    return n

def ceildiv(n,d):
    if d<=0:raise ValueError('nonpositive denominator')
    return (n+d-1)//d

def parse(program):
    records=[];cursor=0
    while cursor<len(program):
        if cursor+2>len(program):raise ValueError('truncated opcode header')
        opcode,length=program[cursor:cursor+2];cursor+=2
        if cursor+length>len(program):raise ValueError('truncated instruction')
        records.append((opcode,program[cursor:cursor+length]));cursor+=length
    if [(op,len(args)) for op,args in records]!=[(33,20),(28,24),(18,64),(21,4),(17,0),(20,8)]:
        raise ValueError('unverified Aqua instruction sequence')
    protocol=records[1][1];curve=records[2][1]
    config=dict(permission_token='0x'+records[0][1].hex(),protocol_fee=int.from_bytes(protocol[:4],'big'),
                fee_recipient='0x'+protocol[4:].hex(),sqrt_min=int.from_bytes(curve[:32],'big'),
                sqrt_max=int.from_bytes(curve[32:],'big'),flat_fee=int.from_bytes(records[3][1],'big'))
    if not 0<config['sqrt_min']<config['sqrt_max'] or max(config['protocol_fee'],config['flat_fee'])>=FEE_SCALE:
        raise ValueError('invalid curve bounds or fee')
    return config

def quote_exact_input(program,token_in,token_out,balance_in,balance_out,amount):
    c=parse(program)
    for n in (balance_in,balance_out,amount):checked(n)
    if not amount or not balance_in or not balance_out:raise ValueError('zero input/reserve')
    lt=int(token_in,16)<int(token_out,16)
    if token_in.lower()==token_out.lower():raise ValueError('same token')
    a,b=(balance_in,balance_out) if lt else (balance_out,balance_in)
    lo,hi=c['sqrt_min'],c['sqrt_max']
    alpha=ONE-lo*ONE//hi
    beta=checked(a*lo//ONE+b*ONE//hi)
    four_ac=checked((4*alpha*a//ONE)*b)
    disc=checked(checked(beta*beta)+four_ac)
    liquidity=checked((beta+isqrt(disc))*ONE//(2*alpha)) if alpha else 0
    if not liquidity:raise ValueError('zero effective liquidity')
    if lt:
        vin=checked(balance_in+ceildiv(checked(liquidity*ONE),hi));vout=checked(balance_out+liquidity*lo//ONE)
    else:
        vin=checked(balance_in+ceildiv(checked(liquidity*lo),ONE));vout=checked(balance_out+liquidity*ONE//hi)
    protocol_fee=checked(amount*c['protocol_fee'])//FEE_SCALE
    net=amount-protocol_fee
    lp_fee=ceildiv(checked(net*c['flat_fee']),FEE_SCALE)
    net-=lp_fee
    out=checked(net*vout)//checked(vin+net)
    return dict(amount_in=amount,amount_out=out,protocol_fee=protocol_fee,flat_fee=lp_fee,
                liquidity=liquidity,virtual_in=vin,virtual_out=vout,permission_assumed=True)


def transition_exact_input(program,token_in,token_out,packed_in,packed_out,amount):
    """Candidate for verified routes repaying full input; caller commits atomically.

    Only use after verifying the router's push settlement. Permission/funding
    remain assumed; no state is mutated here.
    """
    from hub_state import unpack,withdraw,deposit
    fi,bi=unpack(packed_in);fo,bo=unpack(packed_out)
    if fi in (0,255) or fo in (0,255):raise ValueError('inactive Aqua allocation')
    q=quote_exact_input(program,token_in,token_out,bi,bo,amount)
    return dict(quote=q,allocation_in=deposit(withdraw(packed_in,q['protocol_fee']),amount),
                allocation_out=withdraw(packed_out,q['amount_out']))
