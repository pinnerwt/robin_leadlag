"""Offline initialization-key inventory for delegated index4 dependencies.
No RPC; missing values stay missing. Bitmap range is bounded and not full-domain.
"""
import argparse,json
from pathlib import Path
from bootstrap_state import mapping
from index4_local import FEE,FACTORY
HELPER='0xaa48aaef655fb7cd7acc04717f66022a4771a345'

def inventory(seed,plan,*,caller,origin,block,bitmap_radius=2):
 if type(bitmap_radius) is not int or not 0<=bitmap_radius<=16:raise ValueError('bitmap radius')
 accounts=seed['accounts'];keys={};unresolved=[];pools=[]
 def want(address,key,reason):
  key=hex(int(key,16)) if isinstance(key,str) else hex(key)
  row=keys.setdefault((address,key),dict(address=address,slot=key,reasons=[]))
  if reason not in row['reasons']:row['reasons'].append(reason)
  raw={int(k,16):int(v,16) for k,v in accounts.get(address,{}).get('storage',{}).items()}
  row['present']=int(key,16) in raw
  return raw.get(int(key,16))
 for action in plan['actions']:
  pool=action['target'];code=accounts.get(pool,{}).get('code','')
  if code!='0x363d3d373d3d3d363d731642634c8cb1c9f1b84c9a1a08534f8c3f4e89f85af43d82803e903d91602b57fd5bf3':continue
  pools.append(pool)
  packed=want(pool,6,'pool slot0');settings=want(pool,12,'pool settings');want(pool,13,'active liquidity')
  want(FEE,2,'fee observation window');want(FEE,mapping(int(pool,16),3),'fee config')
  want(FEE,mapping(block,int(mapping(int(pool,16),4),16)),'fee cache at requested block')
  if packed is None or settings is None:
   unresolved.append(dict(pool=pool,reason='core state required to derive observation/bitmap keys'));continue
  card=packed>>200&65535;next_card=packed>>216&65535;index=packed>>184&65535
  if not 0<=index<card<=next_card<=65535:raise ValueError('invalid observation bounds')
  for i in range(next_card):want(pool,17+i,'observation ring')
  spacing=settings>>176&0xffffff
  if not 0<spacing<1<<23:raise ValueError('invalid spacing')
  want(FACTORY,mapping(spacing,15),'zero-fee fallback')
  tick=packed>>160&0xffffff;tick=tick-(1<<24) if tick&(1<<23) else tick;center=(tick//spacing)>>8
  for i in range(center-bitmap_radius,center+bitmap_radius+1):
   bits=want(pool,mapping(i,15),'bounded bitmap')
   if bits is None:
    unresolved.append(dict(pool=pool,bitmap_word=i,reason='bitmap required to derive initialized tick keys'));continue
   for bit in range(256):
    if bits>>bit&1:want(pool,mapping((i*256+bit)*spacing,14),'initialized tick liquidity')
  for actor in sorted({caller.lower(),origin.lower()}):
   base=int(mapping(int(actor,16),2),16)
   profile=want(HELPER,base,'caller/origin discount')
   # Verified helper layout: mapping2 profile + 1 is the pool-rate mapping.
   # Fetch when the enable flag is unknown too, avoiding another bootstrap pass.
   if profile is None or profile&255:
    want(HELPER,mapping(int(pool,16),(base+1)%(1<<256)),'pool-specific caller/origin discount')
 rows=sorted(keys.values(),key=lambda r:(r['address'],int(r['slot'],16)))
 return dict(anchor=seed['anchor']['hash'],block=block,pools=pools,keys=rows,unresolved=unresolved,
  missing=sum(not r['present'] for r in rows),complete=False,
  caveat='Initialization inventory only. Rewards/post-hooks, token accounting and code pins not covered; bounded bitmap is not arbitrary-size coverage.')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',default='reports/amm/delegated-initialization-manifest.json');a=ap.parse_args()
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
 case=next(c for c in json.loads(Path('reports/amm/delegated-single-callback-probe.json').read_text())['cases'] if c['tx']['tx'].startswith('0x9bc1'))
 out=inventory(seed,case['plan'],caller=case['tx']['to'],origin=case['tx']['from'],block=int(seed['anchor']['number'],16))
 Path(a.output).write_text(json.dumps(out,indent=2)+'\n')
 print(dict(pools=len(out['pools']),keys=len(out['keys']),missing=out['missing'],unresolved=len(out['unresolved'])))
if __name__=='__main__':main()
