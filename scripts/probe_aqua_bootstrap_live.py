"""Explicit read-only fixed-block Aqua bootstrap smoke, never a hot-path worker."""
import json
from pathlib import Path
from bootstrap_state import Bootstrap
from bootstrap_aqua import refresh_aqua
from router_registry import refresh_registry
from aqua_book import C9,R777

def main():
 rpc=Bootstrap('https://rpc-robinhood.blockmachine.io',interval=0.7)
 anchor=rpc.rpc('eth_getBlockByNumber',['latest',False])
 template=json.loads(Path('config/aqua-router-template.json').read_text())
 template['routers']={a:template['routers'][a] for a in (C9,R777)}
 registry=refresh_registry(template,anchor,rpc.rpc)
 aqua=refresh_aqua(json.loads(Path('config/aqua-template.json').read_text()),anchor,rpc.rpc)
 result=dict(anchor=anchor,registry=registry,aqua=aqua,rpc_calls=rpc.calls,
             caveat='Current fixed-block Aqua subset; no V3 snapshot and no recorder started')
 Path('reports/amm/aqua-live-bootstrap.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(dict(block=anchor['number'],hash=anchor['hash'],strategies=len(aqua['strategies']),router_inventory=aqua['router_inventory'],rpc_calls=rpc.calls)))
if __name__=='__main__':main()
