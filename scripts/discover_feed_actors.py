"""Build startup actor inventory from decoded feed strictly before a new anchor.
Only address identities are retained; never copy transaction-derived state values.
"""
import argparse,json,re
from pathlib import Path
ADDRESS=re.compile(r'^0x[0-9a-fA-F]{40}$')
def discover(lines,anchor):
 actors={}
 for line in lines:
  r=json.loads(line)
  if not (r.get('kind')=='feed_tx' or (r.get('kind')=='feed_system_tx' and r.get('system_kind')=='eth_deposit')) or r['sequence']>=anchor:continue
  for field in ('from','to'):
   a=r.get(field)
   if a is None:continue
   if not isinstance(a,str) or not ADDRESS.fullmatch(a):raise ValueError('invalid feed actor')
   a=a.lower();actors[a]=max(actors.get(a,0),r['sequence'])
 return [dict(from_address=a,sequence=s) for a,s in sorted(actors.items())]
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('decoded',type=Path);p.add_argument('--anchor',type=lambda s:int(s,0),required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 with a.decoded.open() as f:rows=discover(f,a.anchor)
 with a.output.open('w') as out:
  for r in rows:out.write(json.dumps({'from':r['from_address'],'sequence':r['sequence']},separators=(',',':'))+'\n')
 print('pre-anchor actors',len(rows))
