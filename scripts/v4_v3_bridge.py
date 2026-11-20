"""Experimental atomic V4 -> V3 reducer for verified 10000c shape.

Uses preloaded, same-anchor pool states and known router inventories. Hook
flag=true is required explicitly. Native recipient execution is not modeled.
"""
import copy
from v3_calldata import word,array,blob,path,address
from universal_v4_intent import inspect
WETH='0x0bd7d308f8e1639fab988df18a8011f41eacad73'

def pool_key(op):return tuple(op[k] for k in ('currency0','currency1','fee','tick_spacing','hooks'))

def plan(calldata):
    raw=bytes.fromhex(calldata.removeprefix('0x'))
    if raw[:4].hex()!='3593564c':raise ValueError('Universal selector')
    d=raw[4:];commands=blob(d,word(d,0));inputs=array(d,word(d,1))
    if commands!=b'\x10\x00\x0c' or len(inputs)!=3:raise ValueError('V4/V3 sequence not verified')
    v4,swap,unwrap=inputs;op=inspect(v4)
    actions=blob(v4,word(v4,0));args=array(v4,word(v4,1))
    if actions!=b'\x06\x0c\x0e' or not op['zero']:raise ValueError('V4 funding branch not verified')
    settle,take=args[1:]
    if len(settle)!=64 or address(word(settle,0))!=op['currency0'] or word(settle,1)!=-op['amount']:
        raise ValueError('V4 settle-all mismatch')
    if len(take)!=96 or address(word(take,0))!=op['currency1'] or word(take,1)!=2 or word(take,2)!=0:
        raise ValueError('V4 take-all mismatch')
    if len(swap)!=256 or word(swap,0)!=2 or word(swap,1)!=1<<255 or word(swap,3)!=160 or word(swap,4)!=0:
        raise ValueError('V3 balance-based mode')
    hops=path(blob(swap,160))
    if len(hops)!=1:raise ValueError('V3 multihop')
    inp,out,fee=hops[0]
    if inp!=op['currency1'] or out!=WETH:raise ValueError('V4/V3 tokens mismatch')
    if len(unwrap)!=64 or word(unwrap,0)!=1:raise ValueError('unwrap recipient mode')
    return dict(v4=op,v3_in=inp,v3_out=out,v3_fee=fee,partial_reason='native recipient execution not modeled')

class Bridge:
    def __init__(self,v4_state,v4_key,v3_states,v3_meta,inventory,flags,anchors):
        if len(anchors)!=3 or len(set(anchors))!=1:raise ValueError('pool/inventory/flags anchors differ')
        self.v4=copy.deepcopy(v4_state);self.key=pool_key(v4_key)
        self.states=copy.deepcopy(v3_states);self.meta=copy.deepcopy(v3_meta)
        self.inventory=dict(inventory);self.flags=dict(flags)
        if any(not isinstance(v,int) or not 0<=v<1<<256 for v in self.inventory.values()):raise ValueError('invalid router inventory')
        self.valid=True
    def invalidate(self,reason):self.valid=False;self.reason=reason
    def apply(self,calldata,sender):
        if not self.valid:raise ValueError('bridge invalid: '+self.reason)
        route=plan(calldata);op=route['v4']
        if pool_key(op)!=self.key:raise ValueError('unknown V4 pool')
        if self.flags.get(sender.lower()) is not True:raise ValueError('unknown or non-exempt hook flag')
        inp,out=route['v3_in'],route['v3_out']
        if inp not in self.inventory or out not in self.inventory:raise ValueError('missing router inventory')
        matches=[a for a,p in self.meta.items() if p['fee']==route['v3_fee'] and set(p['tokens'])=={inp,out}]
        if len(matches)!=1:raise ValueError('missing or ambiguous downstream pool')
        pool=matches[0];v4=copy.deepcopy(self.v4);v3=copy.deepcopy(self.states[pool]);inv=dict(self.inventory)
        first=v4.swap(op['zero'],-op['amount'],op['limit'],True)
        # State uses pool deltas; V4 manager uses their negatives.
        received=-first['amount1'];inv[inp]+=received
        if received<0 or inv[inp]>=1<<255:raise ValueError('invalid dependent amount')
        zero=self.meta[pool]['tokens'][0]==inp
        second=v3.swap(zero,inv[inp],None,True)
        spent=second['amount0'] if zero else second['amount1']
        output=-second['amount1'] if zero else -second['amount0']
        if not 0<=spent<=inv[inp] or output<0:raise ValueError('invalid V3 flow')
        inv[inp]-=spent;inv[out]+=output
        if inv[out]>=1<<256:raise ValueError('router inventory overflow')
        unwrapped=inv[out];inv[out]=0
        self.v4=v4;self.states[pool]=v3;self.inventory=inv
        return dict(v4=first,v3=second,pool=pool,v3_requested_input=spent+inv[inp],unwrapped=unwrapped,
                    transaction_success_assumed=True,state_complete=False,partial_reason=route['partial_reason'])
