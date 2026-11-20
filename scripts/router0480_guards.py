"""Observed compressed offset table and leading a1/a2 sqrt-price guards only."""
from router0480_extended_guards import decode as extended_guard
from router0480_reserve_guard import decode as reserve_guard,failed as reserve_failed

def inspect(calldata):
 raw=bytes.fromhex(calldata.removeprefix('0x'))
 if len(raw)<4 or not 0<raw[0]<=64 or raw[1]!=0:raise ValueError('unverified offset table header')
 count=raw[0];end=2+2*count
 if end>len(raw):raise ValueError('truncated offset table')
 offsets=[int.from_bytes(raw[2+2*i:4+2*i],'big') for i in range(count)]
 if offsets!=sorted(set(offsets)) or offsets[0]<end or offsets[-1]>=len(raw):raise ValueError('invalid command offsets')
 guards=[]
 for i,offset in enumerate(offsets):
  if raw[offset] not in (0xa1,0xa2,0xa4,0xa8,0xb8,0xac):break
  stop=offsets[i+1] if i+1<count else len(raw)
  if raw[offset] in (0xb8,0xac):
   guards.append(extended_guard(raw,offset,stop,end,offsets[0]));continue
  if raw[offset]==0xa8:
   c=raw[offset:stop]
   if len(c)!=38 or c[1] not in (0,1):raise ValueError('unverified V4 guard profile')
   manageroff=int.from_bytes(c[2:4],'big');limitoff=int.from_bytes(c[36:38],'big')
   if any(not end<=v<=offsets[0]-20 for v in (manageroff,limitoff)):raise ValueError('V4 guard pointer bounds')
   limit=int.from_bytes(raw[limitoff:limitoff+20],'big')
   if not limit:raise ValueError('zero guard limit')
   guards.append(dict(opcode=168,pool='0x'+c[4:36].hex(),manager='0x'+raw[manageroff:manageroff+20].hex(),getter='0x1e2eaeaf',storage_mapping_slot=6,side=c[1],limit=limit,offset=offset,limit_offset=limitoff));continue
  if raw[offset]==0xa4:
   guards.append(reserve_guard(raw,offset,stop,end,offsets[0]));continue
  if stop-offset!=6:raise ValueError('unverified a1 width')
  side=raw[offset+1];pooloff=int.from_bytes(raw[offset+2:offset+4],'big');limitoff=int.from_bytes(raw[offset+4:offset+6],'big')
  if side not in (0,1) or not end<=pooloff<=offsets[0]-20 or not end<=limitoff<=offsets[0]-20:raise ValueError('invalid a1 operand')
  if int.from_bytes(raw[limitoff:limitoff+20],'big')==0:raise ValueError('zero guard limit')
  guards.append(dict(opcode=raw[offset],getter='0x3850c7bd' if raw[offset]==0xa1 else '0xe76c01e4',pool='0x'+raw[pooloff:pooloff+20].hex(),limit=int.from_bytes(raw[limitoff:limitoff+20],'big'),side=side,offset=offset,limit_offset=limitoff))
 if not guards:raise ValueError('no verified leading price guards')
 return dict(guards=guards,offsets=offsets,remaining_opcodes=[raw[o] for o in offsets[len(guards):]],scope_verified=False)
def evaluate(plan,sqrt_prices):
 for i,g in enumerate(plan['guards']):
  if g['pool'] not in sqrt_prices:raise ValueError('missing guard price')
  p=sqrt_prices[g['pool']]
  if g.get('opcode')==164:
   if reserve_failed(g,p):return dict(skip=True,failed_guard=i)
   continue
  if type(p) is not int or not 0<p<1<<160:raise ValueError('invalid sqrt price')
  if p<g['limit'] if g['side']==1 else p>g['limit']:return dict(skip=True,failed_guard=i)
 return dict(skip=False,failed_guard=None)
