"""Initialization/research only: validate signed-feed unit accounting against
historical transaction traces. Never used by the runtime follower.
"""
import argparse,json
from pathlib import Path
from arbos_units import ARBOS,UNITS,ROOT,signed_units
from bootstrap_state import Bootstrap
p=argparse.ArgumentParser(description=__doc__);p.add_argument('transactions');p.add_argument('--limit',type=int,default=3);a=p.parse_args();b=Bootstrap('https://rpc-robinhood.blockmachine.io');out=[]
for line in open(a.transactions):
 tx=json.loads(line)
 if tx['kind']!='feed_tx':continue
 pre=b.rpc('debug_traceTransaction',[tx['tx'],{'tracer':'prestateTracer'}]);diff=b.rpc('debug_traceTransaction',[tx['tx'],{'tracer':'prestateTracer','tracerConfig':{'diffMode':True}}])
 slots={hex(int(k,16)):int(v,16) for k,v in pre[ARBOS]['storage'].items()};quality=slots[ROOT+'07'];version=slots[ROOT+'00']
 before=int(diff['pre'][ARBOS]['storage'][UNITS],16);after=int(diff['post'][ARBOS]['storage'][UNITS],16);actual=(after-before)%2**64
 expected=signed_units(bytes.fromhex(tx['raw_transaction'][2:]),quality)
 row=dict(tx=tx['tx'],quality=quality,arbos_version=version,expected=expected,actual=actual,matched=actual==expected);out.append(row);print(json.dumps(row),flush=True)
 if len(out)>=a.limit:break
Path('reports/amm/signed-units-parity.json').write_text(json.dumps(out,indent=2)+'\n')
if not all(r['matched'] for r in out):raise SystemExit('signed unit mismatch')
