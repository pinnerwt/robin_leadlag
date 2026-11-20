"""Provisional local V3 candidate for decoded A3D routes; never commits a Book.

This models supported route arithmetic and sequential fills. Router economic
branch selection, final oracle/gas checks and final balance settlement are not
complete: callers must not treat this preview as a production transaction decoder.
No logs, RPC, subprocesses or network are used here.
"""
import copy
from routera3d_price import route_fields, block_window, reverse_v3_limit, forward_v3_limit
from v3_state import State
from routera3d_v4 import reverse_intent,forward_intent,dynamic_intent,POOL_ID

WETH='0x0bd7d308f8e1639fab988df18a8011f41eacad73'
USDG='0x5fc5360d0400a0fd4f2af552add042d716f1d168'
POOLS={0:('0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca',100),
       1:('0x69bfaf19c9f377bb306a89aed9f6b07e2c1a8d9a',500)}

class Candidate:
    def __init__(self, seed, inventory_seed, v4_seed=None):
        if not seed.get('complete') or seed['anchor']['hash']!=inventory_seed['anchor_hash']:
            raise ValueError('complete matching-anchor snapshot required')
        self.meta={p['pool']:p for p in seed['pools']}
        self.states={a:State.load(p) for a,p in self.meta.items()}
        self.v4_seed=copy.deepcopy(v4_seed)
        if v4_seed is not None:
            if v4_seed.get('anchor_hash')!=seed['anchor']['hash'] or v4_seed.get('pool_id')!=POOL_ID:
                raise ValueError('matching V4 pool and anchor required')
            state=State.load(v4_seed['state'])
            if state.spacing!=1 or not 0<=state.fee<1000000:
                raise ValueError('unverified V4 curve profile')
            if 'hook_state' in v4_seed:
                from routera3d_hook import reverse_update
                reference=v4_seed['hook_state']
                if type(reference) is not int:raise ValueError('invalid hook state')
                reverse_update(reference,v4_seed.get('hook_config'),state.sqrt,reference&((1<<40)-1))
            elif v4_seed.get('hook_fee_ppm')!=40 or state.fee!=40:
                raise ValueError('unverified V4 curve profile')
            self.states[POOL_ID]=state
        self.inventory={token:int(inventory_seed['balances'][token]) for token in (WETH,USDG)}
        if any(not 0<=amount<1<<256 for amount in self.inventory.values()):
            raise ValueError('inventory bounds')

    def preview(self, calldata, *, block=None, router_slot9=None):
        plan=route_fields(calldata)
        if router_slot9 is not None:
            if not block_window(calldata,block,router_slot9)['valid']:
                raise ValueError('router calldata outside block window')
        dynamic=self.v4_seed is not None and 'hook_state' in self.v4_seed
        hook_state=self.v4_seed['hook_state'] if dynamic else None
        if dynamic and (type(block) is not int or not 0<=block<1<<40):
            raise ValueError('explicit V4 block required')
        if plan['mode']!=0xe0:
            raise ValueError('mode 40 final fields not modeled')
        if sum(r['index']==6 for r in plan['routes'])>1:
            raise ValueError('repeated V4 route requires hook state transition')
        # Preflight all dependencies before calculating any fill. A missing
        # unrecorded pool cannot be skipped if its output feeds later inventory.
        for position,route in enumerate(plan['routes']):
            if route['index']==6:
                if self.v4_seed is None:raise ValueError('V4 route state required')
                if dynamic:
                    dynamic_intent(calldata,position,1,hook_state=hook_state,hook_config=self.v4_seed['hook_config'],sqrt=self.states[POOL_ID].sqrt,block=block)
                elif route['side']==2:
                    forward_intent(calldata,position,1,hook_fee_ppm=self.v4_seed.get('sell_hook_fee_ppm'))
                else:
                    reverse_intent(calldata,position,1,hook_fee_ppm=self.v4_seed['hook_fee_ppm'])
                continue
            if route['index'] not in POOLS or route['flags']!=9 or route['adjustment']>=0:
                raise ValueError('unverified route descriptor')
            pool,fee=POOLS[route['index']]
            if pool not in self.meta:
                raise ValueError('route pool state required, even when not recorded for quotes')
            meta=self.meta[pool]
            if meta['tokens']!=[WETH,USDG] or int(meta['fee'])!=fee:
                raise ValueError('pool identity mismatch')
        states=copy.deepcopy(self.states); inventory=dict(self.inventory); fills=[]
        for position,route in enumerate(plan['routes']):
            if route['index']==6:
                zero=route['side']==2
                state=states[POOL_ID]
                if dynamic:
                    intent=dynamic_intent(calldata,position,inventory[WETH if zero else USDG],hook_state=hook_state,
                                          hook_config=self.v4_seed['hook_config'],sqrt=state.sqrt,block=block)
                    fee=intent['hook_fee_ppm'];hook_state=intent['hook_state_after']
                else:
                    fee=self.v4_seed['sell_hook_fee_ppm'] if zero else self.v4_seed['hook_fee_ppm']
                    intent=(forward_intent if zero else reverse_intent)(calldata,position,inventory[WETH if zero else USDG],hook_fee_ppm=fee)
                before=dict(inventory);state.fee=fee
                result=state.swap(zero,-intent['amount'],intent['limit'],True)
                inventory[WETH]-=result['amount0'];inventory[USDG]-=result['amount1']
                if any(not 0<=n<1<<256 for n in inventory.values()):raise ValueError('candidate inventory bounds')
                fills.append(dict(pool=POOL_ID,zero=zero,amount=-intent['amount'],limit=intent['limit'],result=result,
                                  inventory_before=before,inventory_after=dict(inventory),native_wrapped=not zero,native_unwrapped=zero))
                continue
            pool,fee=POOLS[route['index']]; state=states[pool]
            discount=-route['adjustment']; adjusted=plan['price']*(100000-discount)//100000
            if not adjusted:raise ValueError('zero adjusted price')
            zero=route['side']==2; token=WETH if zero else USDG
            cap=plan['cap']*10**18//adjusted if zero else plan['cap']
            amount=min(inventory[token],cap)
            limit=(forward_v3_limit if zero else reverse_v3_limit)(plan['price'],discount,fee,10)
            if not amount or not (limit<state.sqrt if zero else limit>state.sqrt):
                raise ValueError('router no-op/alternative branch requires further decoding')
            before=dict(inventory)
            result=state.swap(zero,amount,limit,True)
            inventory[WETH]-=result['amount0']; inventory[USDG]-=result['amount1']
            if any(not 0<=n<1<<256 for n in inventory.values()):
                raise ValueError('candidate inventory bounds')
            fills.append(dict(pool=pool,zero=zero,amount=amount,limit=limit,result=result,
                              inventory_before=before,inventory_after=dict(inventory)))
        return dict(states=states,inventory=inventory,fills=fills,hook_state=hook_state,state_complete=False,
                    inventory_phase='before_unmodeled_final_settlement',transaction_success_assumed=True)
