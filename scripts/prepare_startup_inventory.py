"""Create causal startup actor/mapping inventories; contains no RPC or state values."""
import argparse,json
from pathlib import Path
from discover_feed_actors import ADDRESS

def prepare(anchor,training,base,discovered,lines,horizon=8192):
 number=int(anchor['number'],16)
 if not training.get('complete') or int(training['training_tip']['number'],16)>=number:raise ValueError('training must complete before anchor')
 actors={};callers={}
 for line in lines:
  r=json.loads(line)
  if not (r.get('kind')=='feed_tx' or (r.get('kind')=='feed_system_tx' and r.get('system_kind')=='eth_deposit')) or r['sequence']>=number:continue
  for field in ('from','to'):
   a=r.get(field)
   if a is None:continue
   if not isinstance(a,str) or not ADDRESS.fullmatch(a):raise ValueError('invalid actor')
   a=a.lower();actors[a]=max(actors.get(a,0),r['sequence'])
  if r.get('kind')=='feed_tx' and r.get('to'):callers.setdefault(r['to'].lower(),set()).add(r['from'].lower())
 if any(int(p.get('discovered_before_block','0x0'),16)>=number for p in base):raise ValueError('base profile discovery must precede anchor')
 base_keys={(p['router'].lower(),p['mapping_slot']) for p in base}
 profiles={(p['router'].lower(),p['mapping_slot']):dict(p) for p in base}
 for p in discovered:
  key=(p['router'].lower(),p['mapping_slot']);old=profiles.get(key)
  # Manual proxy implementation pins differ from root proxy runtime hashes.
  if old and old.get('implementation_slot'):continue
  merged=dict(old or {});merged.update(p);profiles[key]=merged
 for (router,slot),p in profiles.items():
  p['discovered_before_block']=training['training_tip']['number']
  if 'nested_indices' in p:
   if not 1<=horizon<=65536:raise ValueError('nested horizon out of bounds')
   p['nested_indices']=list(range(number+1,number+horizon+1))
  elif 'key_addresses' in p or (router,slot) not in base_keys:
   p['key_addresses']=sorted(set(p.get('key_addresses',[]))|set(training['accounts'])|callers.get(router,set()))
 return [{'from':a,'sequence':s} for a,s in sorted(actors.items())],list(profiles.values())

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('anchor','training','base','discovered','prefix'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--decoded',type=Path,action='append',required=True);p.add_argument('--nested-horizon',type=int,default=8192);a=p.parse_args()
 def lines():
  for path in a.decoded:
   with path.open() as f:yield from f
 actors,profiles=prepare(*[json.loads(getattr(a,k).read_text()) for k in ('anchor','training','base','discovered')],lines(),a.nested_horizon)
 Path(str(a.prefix)+'-actors.jsonl').write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in actors))
 Path(str(a.prefix)+'-profiles.json').write_text(json.dumps(profiles,separators=(',',':'))+'\n')
 print('actors',len(actors),'mapping profiles',len(profiles))
