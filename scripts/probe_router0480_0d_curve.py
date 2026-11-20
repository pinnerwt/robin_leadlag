"""Execute saved manager lock code until callback; no synthetic manager."""
import argparse,json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--enable-clz",action="store_true");args=ap.parse_args()
 row=next(r for r in json.loads(Path('reports/amm/router0480-other-swaps.json').read_text())['cases'] if r['opcode']==13);tx=row['tx'];s=json.loads(Path('captures/startup-v9-dependencies.json').read_text());keep={tx['from'].lower(),tx['to'].lower(),'0x'+'00'*20};s['accounts']={a:v for a,v in s['accounts'].items() if a in keep or a[2:] in tx['data'].lower()};s.update(enable_clz=args.enable_clz,trace_execution=True,trace_hashes=True,getters={},execute_calls=[])
 for c in row['synthetic_zero_inventory']:s['getters'].setdefault(c['to'],{})[c['data']]='0x'+bytes(32).hex()
 c=row['result']['calls'][0];s['execute_calls']=[c['to']+':'+c['data']];r=run(s,tx);stages=[r]
 if not r['error'] and len(r['calls'])==1 and r['calls'][0]['to']==tx['to'].lower():
  cb=r['calls'][0];s['execute_calls'].append(cb['to']+':'+cb['data']);r=run(s,tx);stages.append(r)
 if not r['error'] and len(r['calls'])==1:
  swap=r['calls'][0];s['execute_calls'].append(swap['to']+':'+swap['data']);r=run(s,tx);stages.append(r)
 Path('reports/amm/router0480-0d-curve'+('-clz' if args.enable_clz else '')+'.json').write_text(json.dumps(dict(enable_clz=args.enable_clz,tx=tx,stages=stages,result=r,caveat='Isolated0d command; synthetic zero inventory; saved actual manager bytecode, no original full execution claim.'),indent=2)+'\n');print(json.dumps(dict(error=r['error'],calls=r['calls'])))
if __name__=='__main__':main()
