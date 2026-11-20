"""Current hook code beforeSwap dependency discovery; no RPC in this probe."""
import json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 code=json.loads(Path('reports/amm/delegated-wrapper-hook-code.json').read_text());assert code['anchor_verified']
 prior=json.loads(Path('reports/amm/delegated-wrapper-v4-authorization-code.json').read_text());call=prior['result']['calls'][0]
 raw=bytes.fromhex(call['data'][10:]);w=lambda n:n.to_bytes(32,'big')
 data='0x575e24b4'+(w(int(call['caller'],16))+raw[:256]+w(320)+w(0)).hex()
 seed=dict(anchor=code['anchor'],accounts={code['address']:dict(code=code['code'],balance='0x0',nonce='0x0',storage={})},trace_execution=True)
 h=code['anchor'];tx=dict(to=code['address'],data=data,tx='wrapper-beforeSwap-current',sequence=int(h['number'],16),timestamp=int(h['timestamp'],16),l1_block=int(h.get('l1BlockNumber','0x1'),16),**{'from':call['to']})
 result=run(seed,tx)
 Path('reports/amm/delegated-wrapper-hook-probe.json').write_text(json.dumps(dict(seed=seed,tx=tx,result=result,caveat='New fixed-block code, historical pool-key/input scenario, synthetic account metadata. Persistent storage starts unknown; not a historical swap.'),indent=2)+'\n')
 print(result['error'],result['calls'])
if __name__=='__main__':main()
