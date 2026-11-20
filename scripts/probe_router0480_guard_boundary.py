"""Explicit calldata threshold intervention; actual saved getters, no price mocks."""
import json
from pathlib import Path
from router0480_guards import inspect,evaluate
from probe_delegated_kind8 import run

def main():
 old=json.loads(Path('reports/amm/router0480-local-getters.json').read_text());plan=inspect(old['tx']['data']);seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());seed.update(trace_execution=True,trace_calldata=True,execute_calls=old['execute_calls'],control_targets=[old['tx']['to'].lower()]);prices={g['pool']:int(seed['accounts'][g['pool']]['storage']['0x0'],16)&((1<<160)-1) for g in plan['guards']}
 verdict=evaluate(plan,prices);raw=bytearray.fromhex(old['tx']['data'][2:]);g=plan['guards'][verdict['failed_guard']];raw[g['limit_offset']:g['limit_offset']+20]=prices[g['pool']].to_bytes(20,'big');tx=dict(old['tx'],data='0x'+raw.hex());r=run(seed,tx)
 report=dict(tx=tx,original_tx=old['tx'],changed_guard=verdict['failed_guard'],old_limit=g['limit'],new_limit=prices[g['pool']],local_verdict=evaluate(inspect(tx['data']),prices),result=r,caveat='Synthetic calldata threshold intervention only; actual saved code and pool getters. Not original execution.')
 Path('reports/amm/router0480-guard-boundary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(error=r['error'],success=r['execution_success'],calls=r['calls'],verdict=report['local_verdict'])))
if __name__=='__main__':main()
