"""Background-only fixed-anchor Aqua allocations and C9 inventory snapshot."""
from hub_state import HUB,primary_keys,unpack
from c9_router import C9
from aqua_program import parse
from v3_calldata import word,blob,address

def refresh_aqua(template,anchor,rpc,stopped=None):
 block=anchor['number'];strategies=[];seen=set()
 def call(method,params):
  if stopped is not None and stopped.is_set():raise RuntimeError('Aqua initialization cancelled')
  return rpc(method,params)
 def uint(raw):
  if not isinstance(raw,str) or not raw.startswith('0x') or len(raw)!=66:raise ValueError('noncanonical RPC uint256')
  return int(raw,16)
 for primary in template['primaries']:
  keys=primary_keys(primary)
  identity=(keys['maker'],keys['program_hash'])
  if identity in seen:raise ValueError('duplicate Aqua strategy')
  seen.add(identity)
  d=bytes.fromhex(primary[10:]);desc=d[word(d,0):]
  if word(desc,1)!=1<<254:raise ValueError('unsupported Aqua maker traits')
  program=blob(desc,word(desc,2));parse(program)
  balances={}
  for token,slot in keys['token_slots'].items():
   value=uint(call('eth_getStorageAt',[HUB,slot,block]))
   flags,_=unpack(value)
   if flags in (0,255):raise ValueError('inactive Aqua strategy at checkpoint')
   balances[token]=str(value)
  strategies.append(dict(maker=keys['maker'],program_hash=keys['program_hash'],program=program.hex(),balances=balances))
 if not strategies:raise ValueError('empty Aqua strategy template')
 inventory={}
 for token in template['inventory_tokens']:
  token=address(int(token,16))
  if token in inventory:raise ValueError('duplicate inventory token')
  data='0x70a08231'+int(C9,16).to_bytes(32,'big').hex()
  inventory[token]=str(uint(call('eth_call',[dict(to=token,data=data),block])))
 head=call('eth_getBlockByNumber',[block,False])
 if head['hash']!=anchor['hash']:raise ValueError('Aqua snapshot anchor changed')
 return dict(anchor_hash=anchor['hash'],anchor_number=block,strategies=strategies,router_inventory=inventory)
