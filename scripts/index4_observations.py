"""Local observation reads for the verified index4 packed ring layout.

No RPC, hashing or subprocesses. Timestamp/cumulative wrap is rejected until
separately verified. Unknown allocated records never become zero observations.
"""
from bisect import bisect_left
from dataclasses import dataclass

@dataclass(frozen=True)
class Observation:
    timestamp:int
    tick_cumulative:int
    seconds_per_liquidity:int
    initialized:bool
    @classmethod
    def unpack(cls,value):
        if type(value) is not int or not 0<=value<1<<256:raise ValueError('observation word')
        flag=value>>248
        if flag not in (0,1):raise ValueError('observation flag')
        tick=value>>32&((1<<56)-1)
        if tick&(1<<55):tick-=1<<56
        return cls(value&((1<<32)-1),tick,value>>88&((1<<160)-1),bool(flag))
    def pack(self):
        return self.timestamp|((self.tick_cumulative&((1<<56)-1))<<32)|(self.seconds_per_liquidity<<88)|(int(self.initialized)<<248)
    def advance(self,time,tick,liquidity):
        if not self.initialized or not self.timestamp<=time<1<<32:raise ValueError('unverified timestamp wrap/order')
        if not -887272<=tick<=887272 or not 0<=liquidity<1<<128:raise ValueError('observation inputs')
        delta=time-self.timestamp
        cumulative=self.tick_cumulative+tick*delta
        seconds=self.seconds_per_liquidity+(delta<<128)//max(1,liquidity)
        if not -(1<<55)<=cumulative<1<<55 or not 0<=seconds<1<<160:raise ValueError('unverified cumulative wrap')
        return Observation(time,cumulative,seconds,True)

class Ring:
    def __init__(self,records,index,cardinality,cardinality_next=None):
        if not 0<=index<cardinality<=65535:raise ValueError('observation ring bounds')
        self.index=index;self.cardinality=cardinality;self.records=dict(records)
        self.cardinality_next=cardinality if cardinality_next is None else cardinality_next
        if not cardinality<=self.cardinality_next<=65535:raise ValueError('observation growth bounds')
        if any(i not in records for i in range(cardinality)):raise ValueError('unknown observation record')
        ordered=[records[(index+1+i)%cardinality] for i in range(cardinality)]
        self.ordered=[r for r in ordered if r.initialized]
        if not self.ordered or not records[index].initialized:raise ValueError('uninitialized current observation')
        self.times=[r.timestamp for r in self.ordered]
        if any(a>=b for a,b in zip(self.times,self.times[1:])):raise ValueError('unverified timestamp wrap/order')
    @classmethod
    def load(cls,storage):
        raw={int(k,16):int(v,16) for k,v in storage.items()}
        if 6 not in raw:raise ValueError('missing pool slot0')
        index=raw[6]>>184&65535;cardinality=raw[6]>>200&65535
        records={i:Observation.unpack(raw[17+i]) for i in range(cardinality) if 17+i in raw}
        return cls(records,index,cardinality,raw[6]>>216&65535)
    def observe(self,time,seconds_ago,tick,liquidity):
        if type(seconds_ago) is not int or not 0<=seconds_ago<=time:raise ValueError('observation lookback')
        latest=self.records[self.index]
        if time<latest.timestamp:raise ValueError('unverified timestamp wrap/order')
        target=time-seconds_ago
        if target>=latest.timestamp:
            item=latest.advance(target,tick,liquidity)
            return item.tick_cumulative,item.seconds_per_liquidity
        pos=bisect_left(self.times,target)
        if pos<len(self.times) and self.times[pos]==target:
            item=self.ordered[pos];return item.tick_cumulative,item.seconds_per_liquidity
        if pos==0:raise ValueError('observation older than history')
        before,after=self.ordered[pos-1:pos+1];span=after.timestamp-before.timestamp;delta=target-before.timestamp
        difference=after.tick_cumulative-before.tick_cumulative
        rate=(abs(difference)//span)*(1 if difference>=0 else -1)
        cumulative=before.tick_cumulative+rate*delta
        seconds=before.seconds_per_liquidity+(after.seconds_per_liquidity-before.seconds_per_liquidity)*delta//span
        return cumulative,seconds

    def after_swap(self,time,tick_before,tick_after,liquidity_before):
        """Return a new ring after a successful swap; unchanged tick writes none.

        Requires pre-swap liquidity/tick, not the post-crossing curve state.
        Caller must commit this together with the successful pool transition.
        """
        latest=self.records[self.index]
        if time<latest.timestamp:raise ValueError('unverified timestamp wrap/order')
        if tick_before==tick_after or time==latest.timestamp:return self
        if self.cardinality_next!=self.cardinality:raise ValueError('unverified observation cardinality growth')
        item=latest.advance(time,tick_before,liquidity_before)
        index=(self.index+1)%self.cardinality;records=dict(self.records);records[index]=item
        return Ring(records,index,self.cardinality,self.cardinality_next)
