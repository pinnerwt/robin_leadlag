"""Same-anchor two-leg local preview checked against actual pool executions."""
import json
from pathlib import Path
from variant_v3_checkpoint import load
from variant_v3_bridge import preview

def inputs():
 up=json.loads(Path('reports/amm/variant-v3-settled.json').read_text());down=json.loads(Path('reports/amm/variant-v3-downstream.json').read_text());entry=json.loads(Path('reports/amm/batch-unpinned-plans.json').read_text())['transactions'][1]
 imm=json.loads(Path('reports/amm/variant-v3-immutables.json').read_text())
 meta=dict(pool=up['tx']['to'],tokens=['0x'+imm[k]['output'][-40:] for k in ('token0()','token1()')],fee=10000,spacing=200)
 pools=[meta,dict(pool=down['tx']['to'],tokens=[meta['tokens'][0],'0x5fc5360d0400a0fd4f2af552add042d716f1d168'],fee=100,spacing=1)]
 for r in (up,down):
  if not r['anchor_verified'] or not r['result']['execution_success']:raise ValueError('unverified checkpoint/execution')
 args=dict(upstream=load(up['seed']['accounts'][meta['pool']]['storage'],10000,200),downstream=load(down['seed']['accounts'][down['tx']['to']]['storage'],100,1),pools=pools,anchors=dict(upstream=up['seed']['anchor']['hash'],downstream=down['seed']['anchor']['hash'],inventory=up['seed']['anchor']['hash']),weth_balance=0)
 return entry['plan']['actions'][0]['data'],entry['plan']['actions'][1]['data'],args,(up,down)
def main():
 first,second,args,actual=inputs();result=preview(first,second,**args);checks={}
 for name,r in zip(('upstream','downstream'),actual):
  fill=result[name+'_fill'];out=bytes.fromhex(r['result']['output'][2:]);deltas=[int.from_bytes(out[i:i+32],'big',signed=True) for i in (0,32)]
  words={int(w['slot'],16):int(w['value'],16) for w in r['result']['storage_writes']};slot=words[0];tick=(slot>>160)&((1<<24)-1);tick=tick-(1<<24) if tick&(1<<23) else tick
  checks[name]=dict(deltas=deltas==[fill['amount0'],fill['amount1']],sqrt=fill['sqrt']==slot&((1<<160)-1),tick=fill['tick']==tick,committed=result[name].sqrt==fill['sqrt'])
 report=dict(anchor=args['anchors']['upstream'],checks=checks,upstream_fill=result['upstream_fill'],downstream_fill=result['downstream_fill'],weth_balance=result['weth_balance'],caveat='Same-anchor isolated pool execution parity. Initial WETH inventory explicitly assumed zero, token/callback payments mocked; outer authorization and whole transaction success not verified.')
 Path('reports/amm/variant-v3-bridge-parity.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
 if not all(all(v.values()) for v in checks.values()):raise ValueError('bridge parity failed')
if __name__=='__main__':main()
