"""Offline initialization adapter for the observed native bridge profile.
Hashing occurs here only. Caller supplies inventory provenance; no RPC is issued.
Router/delegation code is pinned at initialization; later changes need lifecycle guards.
"""
from bootstrap_state import hashhex,word,mapping
from delegated_batch_route import inspect,ROUTER,HOLDER,SETTLER
from v4_pool_state import load
from v3_state import State
MANAGER='0x8366a39cc670b4001a1121b8f6a443a643e40951'
HOOK='0xe5e702641ea86f4ae6cc3cdaed2b886f976be044'
PINS={MANAGER:'0xbd3881180b547f5fe817545743cfb4343e96b1bc6640dcd70c106b0066e95626',HOOK:'0xc21b1e6c1b45403e81a581f22ed6d9c747997af1cfdac1b1dc9f4b1d346a10db','0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca':'0x3298b5dd4e6f115074c526a55ad05a36fd73a0034ac22ec6cbaab32cc9c1e8d2'}

IMPLEMENTATION='0x000000009b1d0af20d8c6d0a44e162d11f9b8f00'
ROUTER_PINS={IMPLEMENTATION:'0x7fa1bd2edb51499cb83a324acd9d0f35b31774cf8894e26fc13ac0474f4f57a4',ROUTER:'0x6fd527f43abd8d710ade918e7f70909e870b7dba9db84f0173172e4886263f31',HOLDER:'0x99f5e8edaceacfdd183eb5f1da8a7757b322495b80cf7928db289a1b1a09f799',SETTLER:'0xed95405613cc92e911802b3a8b6bb1adcb29590a358c07d0249a4a49c472d756'}

def validate_router_pins(seed,transaction_target):
 if not isinstance(transaction_target,str):raise ValueError('missing transaction target')
 target=transaction_target.lower()
 code=seed['accounts'].get(target,{}).get('code','')
 if code.lower()!='0xef0100'+IMPLEMENTATION[2:]:raise ValueError('unverified entry delegation')
 for address,expected in ROUTER_PINS.items():
  code=seed['accounts'].get(address,{}).get('code')
  if not code or hashhex(bytes.fromhex(code.removeprefix('0x')))!=expected:raise ValueError('router code pin mismatch '+address)
 return target

def initialize(seed,quotes,calldata,*,inventory,transaction_target):
 anchor=seed['anchor']['hash']
 if not anchor or quotes['anchor']['hash']!=anchor or inventory['anchor']!=anchor:raise ValueError('checkpoint mismatch')
 for name in ('weth_balance','native_balance','usdg_balance'):
  if type(inventory[name]) is not int or not 0<=inventory[name]<1<<256:raise ValueError('invalid inventory')
 validate_router_pins(seed,transaction_target)
 plan=inspect(calldata,quotes['pools']);a=plan['v4'];pool=plan['v3']['pool']
 if a['hook']!=HOOK or pool not in PINS:raise ValueError('unverified pool/hook identity')
 for address in (MANAGER,HOOK,pool):
  code=seed['accounts'][address]['code']
  if hashhex(bytes.fromhex(code.removeprefix('0x')))!=PINS[address]:raise ValueError('code pin mismatch '+address)
 key=dict(currency0=a['currency0'],currency1=a['currency1'],fee=a['fee'],tick_spacing=a['spacing'],hooks=a['hook'])
 poolid=int(hashhex(b''.join(word(v) for v in [int(a['currency0'],16),int(a['currency1'],16),a['fee'],a['spacing'],int(a['hook'],16)])),16)
 base=int(mapping(poolid,10),16);storage={hex(int(k,16)):int(v,16) for k,v in seed['accounts'][HOOK]['storage'].items()}
 if any(hex(base+i) not in storage for i in range(5)):raise ValueError('missing hook pool configuration')
 config=[storage[hex(base+i)] for i in range(5)]
 if config[0]!=((int(a['currency1'],16)<<16)|1) or config[1]!=0 or config[2]!=config[3] or config[4]>>240:
  raise ValueError('unsupported hook configuration branch')
 slots={f'slot{n}':mapping(0,int(mapping(poolid,n),16)) for n in (12,13)}
 if any(s not in storage for s in slots.values()):raise ValueError('missing hook accounting counters')
 meta=next(p for p in quotes['pools'] if p['pool']==pool);raw=seed['accounts'][pool]['storage'];slot0=int(raw['0x0'],16);tick=(slot0>>160)&((1<<24)-1);tick=tick-(1<<24) if tick&(1<<23) else tick
 if (int(meta['sqrt']),int(meta['tick']),int(meta['liquidity']))!=(slot0&((1<<160)-1),tick,int(raw['0x4'],16)):
  raise ValueError('V3 quote and storage core mismatch')
 bridge=dict(v4_curve=load(seed['accounts'][MANAGER]['storage'],key),v4_key=key,v3_curve=State.load(meta),pool_meta=meta,hook_config=config[4],hook_storage=storage,accounting_slots=slots,weth_balance=inventory['weth_balance'],native_balance=inventory['native_balance'])
 return dict(bridge_state=bridge,anchors={k:anchor for k in ('v4','hook','v3','inventory')},usdg_balance=inventory['usdg_balance'])
