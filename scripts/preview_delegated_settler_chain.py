"""Join validated checkpoint V4 output with conditional router trace and local V3 curve.
Not chronological replay or an independently decoded hook fee model.
"""
import json
from pathlib import Path
from delegated_settler_v3 import intent
from v3_state import State
from delegated_hook_fee import native_output_fee

def main():
 upstream=json.loads(Path('reports/amm/delegated-settler-curve.json').read_text());c=upstream['cases'][1]
 ret=next(r for r in c['result']['execution_returns'] if r['selector']=='0xf3cd914c' and r['result']=='Return');net=int(ret['output'],16)>>128
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
 if seed['anchor']['hash']!=upstream['anchor']:raise ValueError('hook checkpoint mismatch')
 read=next(r for r in c['result']['storage_reads'] if r['address']==c['key']['hooks'] and r['pc']==12864)
 config=int(seed['accounts'][read['address']]['storage'][read['slot']],16)
 fee=native_output_fee(config,-c['curve_result']['amount0'])
 if fee['net']!=net:raise ValueError('local hook fee differs from actual manager return')
 net=fee['net']
 plan=next(p['plan'] for p in json.loads(Path('reports/amm/delegated-holder-plans.json').read_text())['transactions'] if p['tx']==c['tx']['tx'])
 quotes=json.loads(Path('captures/startup-v9-quotes.json').read_text())
 if quotes['anchor']['hash']!=upstream['anchor']:raise ValueError('checkpoint mismatch')
 route=intent(plan['actions'][2]['data'],net,quotes['pools'])
 trace=next(x for x in json.loads(Path('reports/amm/delegated-settler-wrapped-'+str(net)+'.json').read_text())['cases'] if x['tx']['tx']==c['tx']['tx'])
 actual=trace['result']['calls'][0];d=bytes.fromhex(actual['data'][10:])
 if actual['to']!=route['pool'] or int.from_bytes(d[64:96],'big',signed=True)!=route['amount']:raise ValueError('router amount mismatch')
 pool=next(p for p in quotes['pools'] if p['pool']==route['pool']);state=State.load(pool);before=state.__dict__.copy();fill=state.swap(route['zero'],route['amount'],route['limit'])
 if fill['unfilled']:raise ValueError('partial downstream fill')
 report=dict(tx=c['tx']['tx'],anchor=upstream['anchor'],v4_gross=-c['curve_result']['amount0'],v4_net=net,local_hook_fee=fee,v3_intent=route,v3_before=before,v3_after=state.__dict__,v3_fill=fill,
  caveat='Same-checkpoint conditional chain preview. V4 fee computed locally for verified branch and checked against actual isolated EVM, synthetic full funding/wrap trace, V3 local curve only. No historical prestate, downstream EVM parity or full transaction success claim.')
 Path('reports/amm/delegated-settler-chain-preview.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(v4_net=net,v3_input=route['amount'],v3_fill=fill)))
if __name__=='__main__':main()
