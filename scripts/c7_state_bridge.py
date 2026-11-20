"""Shared C7/router777 Aqua -> V3 candidate reducer; no RPC, logs, or subprocesses.

Initial allocations, router WETH inventory and V3 state must share an anchor.
Verified C7 and router777 routes share one book. Other transactions that touch allocations
or router inventory must be handled externally or invalidate this bridge.
"""
import copy
from c9_balance_route import plan,allocation_transition
from v3_state import State
from hub_state import AGGREGATOR,deposit_fields,deposit
from c9_router import C9


def identity(route):
    # Observed maker traits are fixed by plan(); no hashing needed on hot path.
    return (route['maker'],route['program'])


class Bridge:
    def __init__(self,v3_seed,allocation_seed):
        if v3_seed['anchor']['hash']!=allocation_seed['anchor_hash']:
            raise ValueError('checkpoint anchors differ')
        if not v3_seed.get('complete'):raise ValueError('incomplete V3 checkpoint')
        self.meta={p['pool']:p for p in v3_seed['pools']}
        self.states={a:State.load(p) for a,p in self.meta.items()}
        self.allocations={}
        self.strategy_hashes={}
        self.hash_index_complete=True
        for entry in allocation_seed['strategies']:
            key=(entry['maker'].lower(),entry['program'].lower())
            if key in self.allocations:raise ValueError('duplicate Aqua strategy')
            self.allocations[key]={t.lower():int(v) for t,v in entry['balances'].items()}
            if 'program_hash' in entry:
                hash_key=(key[0],entry['program_hash'].lower())
                if hash_key in self.strategy_hashes:raise ValueError('duplicate Aqua strategy hash')
                self.strategy_hashes[hash_key]=key
            else:self.hash_index_complete=False
        self.inventory={t.lower():int(v) for t,v in allocation_seed['router_inventory'].items()}
        self.valid=True

    def invalidate(self,reason):
        self.valid=False
        self.reason=reason

    def apply(self,calldata):
        if not self.valid:raise ValueError('bridge invalid: '+self.reason)
        route=plan(calldata);key=identity(route)
        if key not in self.allocations:raise ValueError('unknown Aqua strategy')
        allocations=self.allocations[key]
        tin,tout=route['token_in'],route['token_out']
        if tin not in allocations or tout not in allocations:raise ValueError('missing Aqua allocation')
        if tout not in self.inventory:raise ValueError('missing router callback inventory')
        proposal=allocation_transition(calldata,allocations[tin],allocations[tout],self.inventory[tout],self.meta)
        if len(proposal['operations'])!=1:
            # Its V3 state can be unrecorded for quotes, but without it we cannot
            # infer how much router inventory the callback actually consumes.
            raise ValueError('callback pool state required to update router inventory')
        op=proposal['operations'][0];pool=op['pool']
        candidate=copy.deepcopy(self.states[pool])
        result=candidate.swap(op['zero'],op['amount'],op['limit'],True)
        spent=result['amount0'] if op['zero'] else result['amount1']
        received=-result['amount1'] if op['zero'] else -result['amount0']
        if not 0<=spent<=proposal['callback_balance'] or received<0:
            raise ValueError('invalid V3 token flow')
        # Preserve residual tokenOut for partial fills. Root's final profit
        # handling uses tokenIn; do not guess its final balance or reuse stale data.
        remaining=proposal['callback_balance']-spent
        updated=dict(allocations)
        updated[tin]=proposal['allocation_in'];updated[tout]=proposal['allocation_out']
        inventory=dict(self.inventory);inventory[tout]=remaining;inventory.pop(tin,None)
        self.states[pool]=candidate
        self.allocations[key]=updated
        self.inventory=inventory
        return dict(aqua=proposal['quote'],v3=result,pool=pool,router_output_inventory=remaining,
                    transaction_success_assumed=True,state_complete=False)

    def apply_hub_push(self,calldata,sender):
        """Direct hub push under the assumed-success policy. Sender determines
        token debits only; no nonce/auth/balanceOf requests are made.
        The caller must verify the transaction target is the pinned Aqua hub.
        """
        if not self.valid:raise ValueError('bridge invalid: '+self.reason)
        op=deposit_fields(calldata)
        if not self.hash_index_complete:raise ValueError('checkpoint missing strategy hashes')
        key=self.strategy_hashes.get((op['maker'],op['program_hash'])) if op['caller']==AGGREGATOR else None
        updated=None
        if key is not None:
            if op['token'] not in self.allocations[key]:raise ValueError('missing deposit token allocation')
            updated=dict(self.allocations[key])
            updated[op['token']]=deposit(updated[op['token']],op['amount'])
        inventory=dict(self.inventory)
        if sender.lower()==C9 and op['maker']!=C9 and op['token'] in inventory:
            if inventory[op['token']]<op['amount']:raise ValueError('router deposit inventory underflow')
            inventory[op['token']]-=op['amount']
        elif sender.lower()!=C9 and op['maker']==C9 and op['token'] in inventory:
            from aqua_program import checked
            inventory[op['token']]=checked(inventory[op['token']]+op['amount'])
        if updated is not None:self.allocations[key]=updated
        self.inventory=inventory
        return dict(allocation_updated=updated is not None,transaction_success_assumed=True)

    def apply_hub_pull(self,calldata,caller):
        """Apply a decoded direct/nested hub call once, using its immediate caller.

        Do not replay internal calls separately after applying a whole C7 route.
        """
        from hub_state import withdrawal_fields,withdraw
        from aqua_program import checked
        if not self.valid:raise ValueError('bridge invalid: '+self.reason)
        op=withdrawal_fields(calldata,caller)
        if not self.hash_index_complete:raise ValueError('checkpoint missing strategy hashes')
        key=self.strategy_hashes.get((op['maker'],op['program_hash'])) if op['caller']==AGGREGATOR else None
        updated=None
        if key is not None:
            if op['token'] not in self.allocations[key]:raise ValueError('missing withdrawal token allocation')
            updated=dict(self.allocations[key])
            updated[op['token']]=withdraw(updated[op['token']],op['amount'])
        inventory=dict(self.inventory)
        if op['token'] in inventory:
            if op['maker']==C9 and op['recipient']!=C9:
                if inventory[op['token']]<op['amount']:raise ValueError('router withdrawal inventory underflow')
                inventory[op['token']]-=op['amount']
            elif op['maker']!=C9 and op['recipient']==C9:
                inventory[op['token']]=checked(inventory[op['token']]+op['amount'])
        if updated is not None:self.allocations[key]=updated
        self.inventory=inventory
        return dict(allocation_updated=updated is not None,transaction_success_assumed=True)

    def apply_router777(self,calldata):
        """Apply 777 against the same allocations and V3 states as C7.

        Successful-transaction policy skips min-output rejection, like the
        optimistic recorder; report the check for research diagnostics. Require
        full V3 consumption since residual 777 inventory is not modeled here.
        """
        from router777_plan import plan as plan777,allocation_candidate
        from v3_calldata import word,blob
        if not self.valid:raise ValueError('bridge invalid: '+self.reason)
        route=plan777(calldata)
        data=bytes.fromhex(route['primary'][10:]);desc=data[word(data,0):]
        key=(route['maker'],blob(desc,word(desc,2)).hex())
        if key not in self.allocations:raise ValueError('unknown Aqua strategy')
        tin,tout=route['token_in'],route['token_out'];balances=self.allocations[key]
        if tin not in balances or tout not in balances:raise ValueError('missing Aqua allocation')
        proposal=allocation_candidate(calldata,balances[tin],balances[tout],self.meta)
        op=proposal['operation'];pool=op['pool'];candidate=copy.deepcopy(self.states[pool])
        result=candidate.swap(op['zero'],op['amount'],op['limit'],True)
        spent=result['amount0'] if op['zero'] else result['amount1']
        received=-result['amount1'] if op['zero'] else -result['amount0']
        if result['unfilled'] or spent!=op['amount'] or received<0:
            raise ValueError('777 residual inventory requires full callback consumption')
        updated=dict(balances);updated[tin]=proposal['allocation_in'];updated[tout]=proposal['allocation_out']
        self.states[pool]=candidate;self.allocations[key]=updated
        # C9 inventory is a different account and must remain untouched.
        return dict(aqua=proposal['quote'],v3=result,pool=pool,
                    minimum_output_met=received>=route['reverse_minimum_output'],
                    transaction_success_assumed=True,state_complete=False)

    def apply_transaction(self,to,calldata):
        """Address-specific dispatch; caller must verify pinned bytecode first."""
        target=to.lower() if to else None
        if target==C9:return self.apply(calldata)
        if target=='0x7777857616fb37f0cfa262e9bb945e828312df17':return self.apply_router777(calldata)
        raise ValueError('unsupported shared Aqua transaction target')
