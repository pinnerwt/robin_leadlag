"""Same-anchor startup-only entry and nested router code discovery."""
import argparse,json
from pathlib import Path
from bootstrap_state import Bootstrap,hashhex
from initialize_batch_bridge import ROUTER_PINS,validate_router_pins

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--latest',action='store_true');args=ap.parse_args()
 h=json.loads(Path('reports/amm/variant-code-checkpoint.json').read_text())['anchor'];entries=json.loads(Path('reports/amm/batch-unpinned-plans.json').read_text())['transactions'];targets=[e['tx']['to'].lower() for e in entries]
 b=Bootstrap('https://rpc-robinhood.blockmachine.io');accounts={}
 if args.latest:h=b.rpc('eth_getBlockByNumber',['latest',False])
 for address in targets+list(ROUTER_PINS):
  accounts[address]=dict(code=b.rpc('eth_getCode',[address,h['number']]))
 verified=b.rpc('eth_getBlockByNumber',[h['number'],False])['hash']==h['hash'];seed=dict(anchor=h,accounts=accounts);checks=[]
 for target in targets:
  try:validate_router_pins(seed,target);error=None
  except ValueError as exc:error=str(exc)
  checks.append(dict(target=target,error=error,code=accounts[target]['code']))
 report=dict(seed=seed,anchor_verified=verified,checks=checks,code_hashes={a:hashhex(bytes.fromhex(v['code'][2:])) for a,v in accounts.items()},rpc_calls=b.calls,caveat='Code identity at new checkpoint only. No old entry-state claim or authorization proof.')
 Path('reports/amm/variant-router-pins-latest.json' if args.latest else 'reports/amm/variant-router-pins.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(verified=verified,checks=checks)))
if __name__=='__main__':main()
