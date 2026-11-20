"""Describe observed ordering, not unobservable competing intent or mempool arrival."""
import json,subprocess
from pathlib import Path
POOL='0xb89fd35ebc48b791339520af812b70f71d823cc5'
r=json.loads(Path('reports/pilot-neighbours-raw.json').read_text());own={w['order']['tx'] for w in r['windows']}
def position(l):return (int(l['blockNumber'],16),int(l['transactionIndex'],16),int(l.get('logIndex','0x0'),16))
worker=subprocess.Popen(['target/release/metric-live-state'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
def decode(tx):
 worker.stdin.write(json.dumps(dict(kind='pyth',data=tx['input']))+'\n');worker.stdin.flush();out=json.loads(worker.stdout.readline());return next((x for x in out.get('result',{}).get('updates',[]) if x['feed']==2),None)
feeds=[]
for l in r['extended_eth_feeds']:
 t=r['transactions'][l['transactionHash']];feeds.append(dict(log=l,update=decode(t)))
rows=[]
for w in r['windows']:
 receipt=w['receipt'];n=int(receipt['blockNumber'],16);ix=int(receipt['transactionIndex'],16);pos=(n,ix,-1)
 before=[f for f in feeds if position(f['log'])<pos];after=[f for f in feeds if position(f['log'])>pos]
 def view(f):
  if not f:return None
  l=f['log'];return dict(block_offset=int(l['blockNumber'],16)-n,transaction_index=int(l['transactionIndex'],16),tx=l['transactionHash'],update=f['update'])
 competitors=[l for l in r['extended_b89_swaps'] if abs(int(l['blockNumber'],16)-n)<=10 and l['transactionHash']not in own]
 v3=[l for l in r['logs'] if l['address'].lower()not in (POOL,'0x30a88bf894d1b806125a23ebf23d715496fd7102') and int(l['blockNumber'],16)==n]
 row=dict(tx=w['order']['tx'],side=w['order']['intent']['side'],success=receipt['status']=='0x1',block=n,index=ix,nearest_provider_before=view(max(before,key=lambda f:position(f['log'])))if before else None,nearest_provider_after=view(min(after,key=lambda f:position(f['log'])))if after else None,other_b89_swaps_within_10_blocks=len(competitors),same_block_v3_before=[dict(index=int(l['transactionIndex'],16),tx=l['transactionHash'],pool=l['address'])for l in v3 if int(l['transactionIndex'],16)<ix],same_block_v3_after=[dict(index=int(l['transactionIndex'],16),tx=l['transactionHash'],pool=l['address'])for l in v3 if int(l['transactionIndex'],16)>ix])
 rows.append(row)
worker.terminate();worker.wait()
other=[]
for l in r['extended_b89_swaps']:
 if l['transactionHash'] in own:continue
 t=r['transactions'][l['transactionHash']];data=bytes.fromhex(l['data'][2:]);db=int.from_bytes(data[32:48],'big',signed=True);dq=int.from_bytes(data[48:64],'big',signed=True)
 other.append(dict(tx=l['transactionHash'],block=int(l['blockNumber'],16),index=int(l['transactionIndex'],16),sender=t['from'],router=t['to'],side='sell'if db>0 else'buy',base_tokens=abs(db)/1e18,usdg=abs(dq)/1e6))
result=dict(rows=rows,extended_range=r['extended_range'],provider_updates=len(feeds),successful_b89_swaps=len(r['extended_b89_swaps']),other_b89_swaps=other,limitations=['Block offsets are exact; converting them to milliseconds is only an estimate.','Successful swap logs do not expose reverted/abandoned competing trades or private arrival times.','Provider and V3 ordering are causal candidates, not proof of the precise revert cause.'])
Path('reports/pilot-crowding.json').write_text(json.dumps(result,indent=2)+'\n')
for row in rows:print(json.dumps(row))
print('other',other)
