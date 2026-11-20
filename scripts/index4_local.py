"""Provisional local index4 quote-state transitions for verified swap branches.

Covers curve, observations and fee cache, not fee-growth/rewards accounting or
full-router execution. Initialization hashes known storage keys; preview performs
no I/O. Caller discount must be supplied from verified local caller/origin settings.
"""
import copy
from dataclasses import dataclass
from bootstrap_state import mapping
from index4_pool_state import load
from index4_observations import Ring
from index4_fee import cached_fee,undiscounted_fee,discounted_fee,integer
POOL='0x7615926023bb149f36095645c2a81dc367d39750'
FEE='0xc0ed888afe87ed1acf01d9f19bb850159e3ce434'
FACTORY='0xc63d7338c178e805c544b8f897066bd3bbcbe136'

@dataclass
class PoolState:
    curve:object
    observations:Ring
    config:int
    window_seconds:int
    fee_cache:dict
    last_block:int
    last_timestamp:int
    caller_discount:int
    fallback_fee:int|None=None

    @classmethod
    def initialize(cls,checkpoint,*,bitmap_words,caller_discount,cache_blocks=(),pool=POOL):
        integer(caller_discount,0,1000000,'caller discount')
        storage=checkpoint['accounts'][pool]['storage']
        fee={int(k,16):int(v,16) for k,v in checkpoint['accounts'][FEE]['storage'].items()}
        block=int(checkpoint['anchor']['number'],16);time=int(checkpoint['anchor']['timestamp'],16)
        config_key=int(mapping(int(pool,16),3),16)
        inner=int(mapping(int(pool,16),4),16);cache={}
        for height in set([block,*cache_blocks]):
            integer(height,block,(1<<64)-1,'initialized cache block')
            key=int(mapping(height,inner),16)
            if key not in fee:raise ValueError('missing fee initialization state')
            cached_fee(fee[key]);cache[height]=fee[key]
        if any(k not in fee for k in (2,config_key)):raise ValueError('missing fee initialization state')
        config=fee[config_key];window=fee[2]&((1<<32)-1)
        # Validate the supported config profile even when the initial cache is set.
        undiscounted_fee(config,0,0,0,window)
        curve=load(storage,effective_fee=0,bitmap_words=bitmap_words)
        factory={int(k,16):int(v,16) for k,v in checkpoint['accounts'].get(FACTORY,{}).get('storage',{}).items()}
        fallback_key=int(mapping(curve.spacing,15),16)
        fallback=(factory[fallback_key]&((1<<24)-1)) if fallback_key in factory else None
        if fallback is not None:integer(fallback,0,999999,'factory fallback fee')
        return cls(curve,Ring.load(storage),config,window,cache,block,time,caller_discount,fallback)

    def preview_exact_input(self,*,block,timestamp,zero,amount,limit=None):
        integer(block,self.last_block,(1<<64)-1,'block')
        integer(timestamp,self.last_timestamp,(1<<32)-1,'timestamp')
        integer(amount,1,(1<<255)-1,'exact input amount')
        if type(zero) is not bool:raise ValueError('swap direction')
        if block not in self.fee_cache:raise ValueError('unknown block fee-cache storage')
        fee=cached_fee(self.fee_cache[block])
        if fee is None:
            old=self.observations.observe(timestamp,self.window_seconds,self.curve.tick,self.curve.liquidity)[0]
            now=self.observations.observe(timestamp,0,self.curve.tick,self.curve.liquidity)[0]
            fee=undiscounted_fee(self.config,self.curve.tick,old,now,self.window_seconds)
        base_fee=fee;fee=discounted_fee(base_fee,self.caller_discount)
        callback_fee=fee
        if fee==0:
            if self.fallback_fee is None:raise ValueError('zero effective fee requires verified pool fallback')
            fee=integer(self.fallback_fee,0,999999,'factory fallback fee')
        curve=copy.deepcopy(self.curve);curve.fee=fee
        result=curve.swap(zero,amount,limit,True)
        observations=self.observations.after_swap(timestamp,self.curve.tick,curve.tick,self.curve.liquidity)
        cache=dict(self.fee_cache);cache[block]=base_fee
        state=PoolState(curve,observations,self.config,self.window_seconds,cache,block,timestamp,self.caller_discount,self.fallback_fee)
        return dict(state=state,result=result,fee=fee,base_fee=base_fee,callback_fee=callback_fee,transaction_success_assumed=True,
                    execution_state_complete=False)
