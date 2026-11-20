"""Pinned router-specific mapping initialization; never called by runtime replay."""
import json,subprocess
from pathlib import Path
from bootstrap_state import hashhex
from bootstrap_accounts import read_accounts
from bootstrap_storage import read_slots

def add_mapping_keys(bootstrap,block,accounts,keys,profile_path):
 profiles=json.loads(Path(profile_path).read_text());evidence=[]
 for profile in profiles:
  if profile.get('discovered_before_block') and int(profile['discovered_before_block'],16)>=int(block,16):raise ValueError('mapping discovery must precede initialization anchor')
  router=profile['router'];pointer_slot=profile.get('implementation_slot')
  if pointer_slot is not None:
   value=read_slots(bootstrap.rpc,block,{router:[pointer_slot]})[router][hex(int(pointer_slot,16))]
   impl='0x'+(int(value,16)&((1<<160)-1)).to_bytes(20,'big').hex()
  else:impl=router
  if impl not in accounts:
   fetched=read_accounts(bootstrap,block,[impl]);accounts[impl]={k:v for k,v in fetched[impl].items() if k!='storage'}
  actual_hash=hashhex(bytes.fromhex(accounts[impl].get('code','0x')[2:]))
  if actual_hash!=profile['implementation_code_hash']:raise ValueError('router mapping implementation changed: '+router)
  addresses=sorted(set(profile.get('key_addresses',accounts)))
  request={'addresses':addresses,'slot':profile['mapping_slot']}
  if 'nested_indices' in profile:
   request['nested_indices']=profile['nested_indices']
   if not request['nested_indices'] or any(type(n)!=int or n<0 or n>=2**64 for n in request['nested_indices']):raise ValueError('nested indices must be explicit nonempty u64 values')
  proc=subprocess.run(['target/release/examples/address_mapping_keys'],input=json.dumps(request),text=True,capture_output=True,check=True)
  entries=json.loads(proc.stdout);keys.setdefault(router,set()).update(int(k,16) for k in entries)
  if pointer_slot is not None:keys[router].add(int(pointer_slot,16))
  item=dict(router=router,implementation=impl,code_hash=actual_hash,entries=len(entries),mapping_slot=profile['mapping_slot'])
  if 'nested_indices' in request:
   item.update(key_addresses=addresses,nested_indices=request['nested_indices'],coverage='explicit_indices_only')
  evidence.append(item)
 return evidence
