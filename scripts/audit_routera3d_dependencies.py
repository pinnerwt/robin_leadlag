"""Offline route relevance audit, not a numeric swap or continuity decoder.

Known trailing unrecorded routes cannot change earlier pool writes under the
assume-success policy. They can still change router inventory for the next tx.
Unknown route identities are never classified as unrecorded.
"""
import argparse
import collections
import json
from pathlib import Path
from routera3d_price import route_fields, mode40_limit_fee_hint
from routera3d_candidate import POOLS
from routera3d_v4 import POOL_ID

ROUTER='0x000000000000a3d2e62895f55d5a4304d2f3c998'
ROUTE_POOLS={**{i:p[0] for i,p in POOLS.items()},
             2:'0xbac3aa3b91584a53a579b3c999a56756e954e59247e497bad1d25a4334bde551',
             4:'0x7615926023bb149f36095645c2a81dc367d39750',
             5:'0xfae65eaa11943f45e83d5b45dc7a7c801c51bfb0',6:POOL_ID}

def classify(calldata, recorded):
    plan=route_fields(calldata)
    recorded={p.lower() for p in recorded}
    routes=[]
    for position,route in enumerate(plan['routes']):
        pool=ROUTE_POOLS.get(route['index'])
        status='unknown_identity' if pool is None else ('recorded' if pool in recorded else 'unrecorded')
        routes.append(dict(position=position,index=route['index'],pool=pool,status=status))
    last=max((r['position'] for r in routes if r['status']=='recorded'),default=-1)
    unknown=[r['position'] for r in routes if r['status']=='unknown_identity']
    upstream=[r['position'] for r in routes if r['status']=='unrecorded' and r['position']<last]
    trailing=[r['position'] for r in routes if r['status']=='unrecorded' and r['position']>last]
    category=('unknown_route_identity' if unknown else
              'unrecorded_before_recorded' if upstream else
              'only_unrecorded' if last<0 else
              'recorded_with_unrecorded_suffix' if trailing else 'recorded_only')
    return dict(category=category,routes=routes,upstream_unrecorded=upstream,
                trailing_unrecorded=trailing,unknown_identity=unknown,
                fee_hint=mode40_limit_fee_hint(calldata) if plan['extra'] else None,
                continuous_inventory_complete=False,
                suffix_omission_scope='earlier recorded pool effects only; requires initial inventory and assumed tx success')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--corpus',default='reports/amm/optimistic-target-corpus.jsonl')
    ap.add_argument('--seed',default='captures/startup-v9-quotes.json')
    ap.add_argument('--output',default='reports/amm/routera3d-dependency-audit.json')
    a=ap.parse_args();seed=json.loads(Path(a.seed).read_text());rows=[]
    for row in map(json.loads,Path(a.corpus).read_text().splitlines()):
        tx=row['tx']
        if (tx.get('to') or '').lower()!=ROUTER:continue
        rows.append(dict(tx=tx['tx'],**classify(tx['data'],[p['pool'] for p in seed['pools']])))
    counts=dict(collections.Counter(r['category'] for r in rows))
    report=dict(anchor=seed['anchor'],transactions=len(rows),counts=counts,
                zero_fee_fallback_transactions=sum(bool(r['fee_hint'] and r['fee_hint']['fallback_required']) for r in rows),
                caveat='Static research route identities; no logs consumed, no numerical fill/parity or production readiness claim.',rows=rows)
    Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','anchor')},indent=2))

if __name__=='__main__':main()
