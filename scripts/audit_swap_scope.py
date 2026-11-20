"""Offline pool-scope audit. Logs are evidence only, never reducer inputs.

The target corpus has filtered logs: absence of an event cannot prove a router
never touches a recorded pool. Only a successful complete decoder returning no
operations establishes an irrelevant route under its verified model.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from amm_feed_state import ROUTERS, SWAP
from v3_calldata import decode
from audit_routera3d_dependencies import classify as route_scope, ROUTER as A3D


from audit_router0480_routes import inspect_route as route0480, ROUTER as ROUTER0480


def dependency_scope(tx, pools, v2_metadata=None):
    """Research route identities only; never promotes numeric decoder coverage."""
    if (tx.get('to') or '').lower() == ROUTER0480:
        try:
            plan = route0480(tx['data'], v2_metadata or {})
        except (ValueError, AttributeError):
            return None
        touched = sorted(set(plan['pools']) & set(pools))
        return dict(category='0480_structural_recorded' if touched else '0480_structural_no_recorded_identity',
                    recorded_pools=touched, route_pools=plan['pools'],
                    execution_complete=False, safe_to_skip=False,
                    unresolved=plan.get('unresolved', ['callback execution and curve state']))
    if (tx.get('to') or '').lower() != A3D:
        return None
    try:
        return route_scope(tx['data'], pools)
    except (ValueError, AttributeError):
        return None


def classify(tx, logs, pools, registry):
    observed = sorted({l['address'].lower() for l in logs
        if l.get('topics', [None])[0] == SWAP and l['address'].lower() in pools})
    try:
        ops = decode(tx.get('to'), tx['data'], pools, ROUTERS, packed_registry=registry)
    except (ValueError, AttributeError) as exc:
        return dict(status='recorded_pool_unresolved' if observed else 'scope_unknown',
                    observed_pools=observed, decoded_pools=[], reason=str(exc))
    touched = sorted({op['pool'] for op in ops})
    missing = sorted(set(observed) - set(touched))
    if missing:
        status = 'recorded_pool_missing_from_decoder'
    elif any(op.get('coverage_note') for op in ops):
        status = 'recorded_pool_partial'
    elif touched:
        status = 'recorded_pool_decoded_intent'
    else:
        status = 'verified_decoder_no_recorded_operation'
    return dict(status=status, observed_pools=observed, decoded_pools=touched, reason=None)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus', default='reports/amm/optimistic-target-corpus.jsonl')
    p.add_argument('--seed', default='captures/startup-v9-quotes.json')
    p.add_argument('--registry', default='config/optimistic-router-template.json')
    p.add_argument('--output', default='reports/amm/swap-scope-audit.json')
    p.add_argument('--v2-metadata', default='reports/amm/router0480-v2-tokens.json')
    a = p.parse_args()
    metadata = json.loads(Path(a.v2_metadata).read_text())
    v2_metadata = {metadata['pool']: dict(tokens=['0x'+metadata['getters'][key]['output'][-40:] for key in ('token0','token1')])}
    pools = {v['pool'].lower(): v for v in json.load(open(a.seed))['pools']}
    registry = json.load(open(a.registry)); rows = []; seen = set()
    for row in map(json.loads, open(a.corpus)):
        tx = row['tx']
        if tx['tx'] in seen:
            raise ValueError('duplicate corpus transaction')
        seen.add(tx['tx'])
        rows.append(dict(tx=tx['tx'], router=(tx.get('to') or '').lower(),
                         selector=tx['data'][:10], **classify(tx, row['logs'], pools, registry),
                         route_scope=dependency_scope(tx, pools, v2_metadata)))
    counts = Counter(r['status'] for r in rows)
    unresolved = Counter((r['router'], pool) for r in rows
        if r['status'] in ('recorded_pool_unresolved', 'recorded_pool_missing_from_decoder')
        for pool in r['observed_pools'] if pool not in r['decoded_pools'])
    structural_pending = Counter(r['router'] for r in rows if r['status'] in ('recorded_pool_unresolved', 'recorded_pool_missing_from_decoder') and r['route_scope'] is None)
    route_counts = Counter(r['route_scope']['category'] for r in rows if r['route_scope'])
    report = dict(counts=dict(counts), research_route_scope_counts=dict(route_counts), no_research_route_scope_by_router=[dict(router=router,transactions=n) for router,n in structural_pending.most_common()], unresolved_by_router_pool=[
        dict(router=router, pool=pool, pair=pools[pool].get('pair'), transactions=n)
        for (router,pool),n in unresolved.most_common()], transactions=rows,
        caveats=['Filtered target-log corpus, not all chain swaps',
                 'Intent decoding is not numeric continuous-state parity',
                 'Unknown scope is never classified as safe to skip',
                 'Research route scope does not promote numeric decoder coverage; suffix omission does not preserve future router inventory',
                 'Stateful Aqua/V4 bridges are not counted as static intent decoders'])
    Path(a.output).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(counts=report['counts'], top_unresolved=report['unresolved_by_router_pool'][:8]), indent=2))

if __name__ == '__main__':
    main()
