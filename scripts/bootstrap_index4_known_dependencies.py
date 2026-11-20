"""Refresh known dependency keys at observation anchor without debug RPC."""
import argparse,json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from bootstrap_state import Bootstrap,mapping
from bootstrap_storage import read_slots
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('observations');ap.add_argument('research_seed');ap.add_argument('--output',required=True);a=ap.parse_args()
obs=json.load(open(a.observations));old=json.load(open(a.research_seed));report=json.load(open('reports/amm/routera3d-index4-execution-probe.json'));head=obs['anchor'];block=head['number']
b=Bootstrap('https://rpc.mainnet.chain.robinhood.com',interval=.1)
if b.rpc('eth_getBlockByNumber',[block,False])['hash']!=head['hash']:raise ValueError('anchor mismatch')
keys={}
for case in report['cases']:
 r=case['result']
 for c in r['execution_calls']:keys.setdefault(c['code'],set())
 for x in r['storage_reads']:keys.setdefault(x['address'],set()).add(int(x['slot'],16))
for address in ['0xaa48aaef655fb7cd7acc04717f66022a4771a345','0x1ad7a8703ebff81c0d753190938f228672ec7e42']:
 keys.setdefault(address,set()).update(int(k,16) for k in old['accounts'][address].get('storage',{}))
for address,slots in keys.items():
 if int(address,16)>0xffff:slots.update(range(32))
# Full known pool curve slots plus explicitly observed ring; no legacy values.
keys[obs['pool']].update(int(k,16) for k in old['accounts'][obs['pool']]['storage'])
keys[obs['pool']].update(int(k,16) for k in obs['accounts'][obs['pool']]['storage'])
fee='0xc0ed888afe87ed1acf01d9f19bb850159e3ce434'
inner=int(mapping(int(obs['pool'],16),4),16)
keys[fee].add(int(mapping(int(block,16),inner),16))
keys['0xaa48aaef655fb7cd7acc04717f66022a4771a345'].add(int(mapping(int('e3c90972c6462bb4a4c75cf49dcf4189c5b42880',16),2),16))
def account(address):
 return address,dict(code=b.rpc('eth_getCode',[address,block]),balance=b.rpc('eth_getBalance',[address,block]),nonce=int(b.rpc('eth_getTransactionCount',[address,block]),16))
with ThreadPoolExecutor(max_workers=4) as pool:accounts=dict(pool.map(account,sorted(keys)))
slots=read_slots(b.rpc,block,{k:sorted(v) for k,v in keys.items() if v})
for address,values in slots.items():accounts[address]['storage']=values
for k,v in obs['accounts'][obs['pool']]['storage'].items():
 if int(accounts[obs['pool']]['storage'][hex(int(k,16))],16)!=int(v,16):raise ValueError('observation mismatch')
if b.rpc('eth_getBlockByNumber',[block,False])['hash']!=head['hash']:raise ValueError('anchor changed')
result=dict(anchor=head,parent_header=head,accounts=accounts,complete=False,execution_state_complete=False,quote_state_complete=False,kind='index4_known_dependency_checkpoint',rpc_phase='initialization_only',rpc_calls=b.calls,caveat='Known keys refreshed at one anchor. Future keys and token settlement dependencies may remain incomplete.')
Path(a.output).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(accounts=len(accounts),slots=sum(map(len,slots.values())),rpc_calls=b.calls,block=block)))
