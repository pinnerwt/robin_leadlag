"""V3 quote state reduced from LOCAL EVM storage writes, never chain log prices.
No network or subprocess on the update/quote path. New mapping keys must be
accompanied by local-EVM KECCAK preimages. Caller owns chain continuity trust.
"""
import copy
from v3_state import State,MIN_TICK,MAX_TICK,MAX256,sqrt_tick
MASK128=(1<<128)-1
MASK160=(1<<160)-1
def signed(v,bits):return v-(1<<bits) if v>>(bits-1) else v
def normalize(storage):return {int(k,16):int(v,16) for k,v in storage.items()}
class StorageBook:
 def __init__(self,seed,layout):
  if not seed.get('complete'):raise ValueError('incomplete V3 checkpoint')
  self.anchor=seed['anchor']['hash'];self.states={};self.maps={};self.ignored={};self.meta={}
  for p in seed['pools']:
   a=p['pool'].lower();state=State.load(p);slots=normalize(seed['accounts'][a]['storage']);m={};ignored=set()
   for key,index in layout[a]['bitmap'].items():
    k=int(key,16);m[k]=('bitmap',index)
    if slots.get(k)!=state.bitmap[index]:raise ValueError('bitmap storage mismatch')
   for key,index in layout[a]['ticks'].items():
    k=int(key,16);m[k]=('tick',index);ignored.update(k+i for i in range(1,4))
    gross,net=state.ticks[index]
    if slots.get(k)!=gross+((net&MASK128)<<128):raise ValueError('tick storage mismatch')
   v=slots[0]
   if (v&MASK160,signed((v>>160)&((1<<24)-1),24),slots[4])!=(state.sqrt,state.tick,state.liquidity):raise ValueError('slot0/liquidity mismatch')
   self.states[a]=state;self.maps[a]=m;self.ignored[a]=ignored;self.meta[a]=p
 def apply(self,writes,mapping_preimages=()):
  """Apply one atomic transaction. Any unmapped large storage write rejects it."""
  touched=set(writes)&set(self.states);states={a:copy.deepcopy(self.states[a]) for a in touched};maps={a:dict(self.maps[a]) for a in touched};ignored={a:set(self.ignored[a]) for a in touched}
  for hint in mapping_preimages:
   a=hint['pool'].lower()
   if a not in touched:continue
   slot=hint['slot'];key=int(hint['key'],16);index=int(hint['index'],16)
   if slot in (5,6):
    index=signed(index,256)
    if slot==5:
     if not MIN_TICK<=index<=MAX_TICK or index%states[a].spacing:raise ValueError('invalid tick key preimage')
     maps[a][key]=('tick',index);ignored[a].update(key+i for i in range(1,4))
    else:
     if index not in states[a].bitmap:raise ValueError('bitmap outside checkpoint coverage')
     maps[a][key]=('bitmap',index)
   elif slot==7:ignored[a].update(key+i for i in range(4))
  for a in touched:
   state=states[a]
   for key,value in normalize(writes[a]).items():
    if key==0:state.sqrt=value&MASK160;state.tick=signed((value>>160)&((1<<24)-1),24)
    elif key==4:state.liquidity=value
    elif key in maps[a]:
     kind,index=maps[a][key]
     if kind=='bitmap':state.bitmap[index]=value
     else:
      gross=value&MASK128;net=signed(value>>128,128)
      if gross:state.ticks[index]=(gross,net)
      else:
       if net:raise ValueError('zero gross with nonzero net')
       state.ticks.pop(index,None)
    elif key in (1,2,3) or 8<=key<8+65535 or key in ignored[a]:pass
    else:raise ValueError('unmapped pool storage write '+hex(key))
   if not 0<=state.liquidity<1<<128:raise ValueError('liquidity range')
   # On a zeroForOne boundary crossing, tick may be one below the price tick.
   if not MIN_TICK<=state.tick<=MAX_TICK or not sqrt_tick(state.tick)<=state.sqrt<=sqrt_tick(min(state.tick+1,MAX_TICK)):raise ValueError('price/tick mismatch')
   if sum(net for gross,net in state.ticks.values())!=0:raise ValueError('net tick liquidity mismatch')
   if sum(net for tick,(gross,net) in state.ticks.items() if tick<=state.tick)!=state.liquidity:raise ValueError('active tick liquidity mismatch')
   expected={w:0 for w in state.bitmap}
   for tick,(gross,net) in state.ticks.items():
    if abs(net)>gross:raise ValueError('tick net exceeds gross')
    c=tick//state.spacing;expected[c>>8]|=1<<(c&255)
   if expected!=state.bitmap:raise ValueError('bitmap/tick mismatch')
  self.states.update(states);self.maps.update(maps);self.ignored.update(ignored);return sorted(touched)
 def quote_raw(self,pool,base_amount):
  if not isinstance(base_amount,int) or base_amount<=0:raise ValueError('positive integral amount required')
  p=self.meta[pool];s=self.states[pool];base=p['base_index'];sell=s.swap(base==0,base_amount);buy=s.swap(base!=0,-base_amount)
  if sell['unfilled'] or buy['unfilled']:raise ValueError('insufficient liquidity for full size')
  key='amount'+str(1-base)
  return dict(bid_amount_raw=abs(sell[key]),ask_amount_raw=abs(buy[key]),base_amount_raw=base_amount)
