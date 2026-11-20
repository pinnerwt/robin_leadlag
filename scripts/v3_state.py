"""Integer Uniswap V3 quote/state engine. Offline only; no I/O or RPC.
TickMath and SwapMath semantics: Uniswap/v3-core (BUSL-1.1, now GPL-2.0-or-later).
Rejects missing tick coverage rather than assuming empty liquidity.
"""
from dataclasses import dataclass,field
Q96=1<<96
MAX256=(1<<256)-1
MIN_TICK=-887272
MAX_TICK=887272
MIN_SQRT=4295128739
MAX_SQRT=1461446703485210103287273052203988822378723970342
FACTORS=[int(x,16) for x in '''fffcb933bd6fad37aa2d162d1a594001 fff97272373d413259a46990580e213a fff2e50f5f656932ef12357cf3c7fdcc ffe5caca7e10e4e61c3624eaa0941cd0 ffcb9843d60f6159c9db58835c926644 ff973b41fa98c081472e6896dfb254c0 ff2ea16466c96a3843ec78b326b52861 fe5dee046a99a2a811c461f1969c3053 fcbe86c7900a88aedcffc83b479aa3a4 f987a7253ac413176f2b074cf7815e54 f3392b0822b70005940c7a398e4b70f3 e7159475a2c29b7443b29c7fa6e889d9 d097f3bdfd2022b8845ad8f792aa5825 a9f746462d870fdf8a65dc1f90e061e5 70d869a156d2a1b890bb3df62baf32f7 31be135f97d08fd981231505542fcfa6 9aa508b5b7a84e1c677de54f3e99bc9 5d6af8dedb81196699c329225ee604 2216e584f5fa1ea926041bedfe98 48a170391f7dc42444e8fa2'''.split()]
def ceil(a,b):
 if b<=0:raise ValueError('nonpositive denominator')
 return (a+b-1)//b
def sqrt_tick(t):
 if abs(t)>MAX_TICK:raise ValueError('tick bounds')
 r=1<<128
 for i,f in enumerate(FACTORS):
  if abs(t)&(1<<i):r=r*f>>128
 if t>0:r=MAX256//r
 return ceil(r,1<<32)
def tick_sqrt(p):
 if not MIN_SQRT<=p<MAX_SQRT:raise ValueError('sqrt bounds')
 lo,hi=MIN_TICK,MAX_TICK
 while lo<hi:
  mid=(lo+hi+1)//2
  if sqrt_tick(mid)<=p:lo=mid
  else:hi=mid-1
 return lo
def amount0(a,b,l,up):
 a,b=sorted((a,b));n=(l<<96)*(b-a)
 return ceil(ceil(n,b),a) if up else n//b//a
def amount1(a,b,l,up):
 n=l*abs(b-a)
 return ceil(n,Q96) if up else n//Q96
def next_price(p,l,amount,zero,exact_in):
 if not l:raise ValueError('zero liquidity')
 n=l<<96
 if zero==exact_in:
  if exact_in:
   product=amount*p
   return ceil(n*p,n+product) if product<=MAX256 and n+product<=MAX256 else ceil(n,n//p+amount)
  if amount*p>=n:raise ValueError('insufficient token0 liquidity')
  return ceil(n*p,n-amount*p)
 if exact_in:return p+amount*Q96//l
 return p-ceil(amount*Q96,l)
@dataclass
class State:
 sqrt:int
 tick:int
 liquidity:int
 fee:int
 spacing:int
 bitmap:dict=field(default_factory=dict)
 ticks:dict=field(default_factory=dict) # tick -> (gross, net)
 @classmethod
 def load(cls,p):
  return cls(int(p['sqrt']),int(p['tick']),int(p['liquidity']),int(p['fee']),int(p['spacing']),{int(k):int(v) for k,v in p['bitmap'].items()},{int(k):tuple(map(int,v)) for k,v in p['ticks'].items()})
 def next_tick(self,tick,zero):
  compressed=tick//self.spacing+(0 if zero else 1);word=compressed>>8;bit=compressed&255
  if word not in self.bitmap:raise ValueError('unknown bitmap word '+str(word))
  mask=((1<<(bit+1))-1) if zero else MAX256^((1<<bit)-1)
  masked=self.bitmap[word]&mask
  step=(masked.bit_length()-1-bit) if zero and masked else ((masked&-masked).bit_length()-1-bit) if masked else (-bit if zero else 255-bit)
  return (compressed+step)*self.spacing,bool(masked)
 def swap(self,zero,amount,limit=None,commit=False):
  if not amount or not -(1<<255)<=amount<(1<<255) or not 0<=self.fee<1000000:raise ValueError('amount/fee')
  p,tick,l=self.sqrt,self.tick,self.liquidity
  limit=limit if limit is not None else MIN_SQRT+1 if zero else MAX_SQRT-1
  if not (MIN_SQRT<limit<p if zero else p<limit<MAX_SQRT):raise ValueError('price limit')
  remaining=abs(amount);ain=aout=0;exact=amount>0;steps=0
  while remaining and p!=limit:
   steps+=1
   if steps>20000:raise ValueError('step limit')
   nt,initialized=self.next_tick(tick,zero);nt=max(MIN_TICK,min(MAX_TICK,nt));boundary=sqrt_tick(nt)
   target=max(limit,boundary) if zero else min(limit,boundary)
   input_target=(amount0 if zero else amount1)(p,target,l,True)
   output_target=(amount1 if zero else amount0)(p,target,l,False)
   budget=remaining*(1000000-self.fee)//1000000 if exact else remaining
   reach=budget>=(input_target if exact else output_target)
   np=target if reach else next_price(p,l,budget,zero,exact)
   used=(amount0 if zero else amount1)(p,np,l,True)
   got=(amount1 if zero else amount0)(p,np,l,False)
   if not exact:got=min(got,remaining)
   fee=remaining-used if exact and np!=target else ceil(used*self.fee,1000000-self.fee)
   remaining-=used+fee if exact else got;ain+=used+fee;aout+=got
   if np==boundary:
    if initialized:
     if nt not in self.ticks:raise ValueError('unknown initialized tick')
     net=self.ticks[nt][1];l+=-net if zero else net
     if not 0<=l<1<<128:raise ValueError('liquidity bounds')
    tick=nt-1 if zero else nt
   elif np!=p:tick=tick_sqrt(np)
   p=np
  if commit:self.sqrt,self.tick,self.liquidity=p,tick,l
  return dict(amount0=ain if zero else -aout,amount1=-aout if zero else ain,sqrt=p,tick=tick,liquidity=l,unfilled=remaining,steps=steps)
 def modify(self,lower,upper,delta):
  if not MIN_TICK<=lower<upper<=MAX_TICK or lower%self.spacing or upper%self.spacing:raise ValueError('tick range')
  changes=[]
  for t,sign in [(lower,1),(upper,-1)]:
   w=(t//self.spacing)>>8
   if w not in self.bitmap:raise ValueError('LP outside seeded bitmap')
   gross,net=self.ticks.get(t,(0,0));gross+=delta;net+=sign*delta
   if not 0<=gross<1<<128:raise ValueError('gross liquidity')
   changes.append((t,w,gross,net))
  liquidity=self.liquidity+(delta if lower<=self.tick<upper else 0)
  if not 0<=liquidity<1<<128:raise ValueError('active liquidity')
  for t,w,gross,net in changes:
   bit=1<<((t//self.spacing)&255)
   if gross:self.ticks[t]=(gross,net);self.bitmap[w]|=bit
   else:self.ticks.pop(t,None);self.bitmap[w]&=MAX256^bit
  self.liquidity=liquidity
