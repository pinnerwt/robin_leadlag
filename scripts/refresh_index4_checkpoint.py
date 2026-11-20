"""One-shot fresh initialization of known keys, observations and nearby ticks."""
import argparse,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from bootstrap_state import Bootstrap,mapping
from bootstrap_storage import read_slots
from bootstrap_index4_observations import snapshot,POOL
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('source');ap.add_argument('--output',required=True);ap.add_argument('--observations',required=True);ap.add_argument('--future-blocks',type=int,default=0);a=ap.parse_args()
if not 0<=a.future_blocks<=1000:raise ValueError('bounded future block range required')
old=json.load(open(a.source));b=Bootstrap('https://rpc.mainnet.chain.robinhood.com',interval=.1);obs=snapshot(b.rpc);head=obs['anchor'];block=head['number']
def meta(address):return address,dict(code=b.rpc('eth_getCode',[address,block]),balance=b.rpc('eth_getBalance',[address,block]),nonce=int(b.rpc('eth_getTransactionCount',[address,block]),16))
with ThreadPoolExecutor(max_workers=4) as ex:accounts=dict(ex.map(meta,old['accounts']))
keys={address:{int(k,16) for k in account.get('storage',{})} for address,account in old['accounts'].items()}
keys[POOL].update(int(k,16) for k in obs['accounts'][POOL]['storage'])
fee='0xc0ed888afe87ed1acf01d9f19bb850159e3ce434';inner=int(mapping(int(POOL,16),4),16)
keys[fee].update(int(mapping(int(block,16)+i,inner),16) for i in range(a.future_blocks+1))
values=read_slots(b.rpc,block,{k:sorted(v) for k,v in keys.items() if v})
for address,v in values.items():accounts[address]['storage']=v
raw={int(k,16):int(v,16) for k,v in accounts[POOL]['storage'].items()};tick=raw[6]>>160&((1<<24)-1);tick=tick-(1<<24) if tick&(1<<23) else tick
spacing=raw[12]>>176&((1<<24)-1);index=(tick//spacing)>>8;bitmap_slot=int(mapping(index,15),16)
if bitmap_slot not in raw:
 extra=read_slots(b.rpc,block,{POOL:[bitmap_slot]})[POOL];accounts[POOL]['storage'].update(extra);raw[bitmap_slot]=int(extra[hex(bitmap_slot)],16)
ticks=[(index*256+i)*spacing for i in range(256) if raw[bitmap_slot]>>i&1]
tick_keys=[int(mapping(t,14),16)+offset for t in ticks for offset in range(8)]
accounts[POOL]['storage'].update(read_slots(b.rpc,block,{POOL:tick_keys})[POOL])
for k,v in obs['accounts'][POOL]['storage'].items():
 if int(accounts[POOL]['storage'][k],16)!=int(v,16):raise ValueError('observation mismatch')
if b.rpc('eth_getBlockByNumber',[block,False])['hash']!=head['hash']:raise ValueError('anchor changed')
result=dict(anchor=head,parent_header=head,accounts=accounts,complete=False,execution_state_complete=False,quote_state_complete=False,kind='index4_known_dependency_checkpoint',rpc_phase='initialization_only',rpc_calls=b.calls,tick_initialization=dict(bitmap_word=index,ticks=ticks,slots_per_tick=8),source_keys_only=a.source,fee_cache_initialized_blocks=list(range(int(block,16),int(block,16)+a.future_blocks+1)))
Path(a.output).write_text(json.dumps(result,indent=2)+'\n');Path(a.observations).write_text(json.dumps(obs,indent=2)+'\n')
print(json.dumps(dict(block=block,accounts=len(accounts),ticks=len(ticks),slots=sum(len(x.get('storage',{})) for x in accounts.values()),rpc_calls=b.calls)))
