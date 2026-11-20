"""Exercise the Rust baseline policy through its replay/shadow input boundary."""
import json,subprocess,tempfile
from pathlib import Path
c=json.loads(Path('config/metric-inventory-shadow.json').read_text())
s=c['stocks']['NVDA']['policy'];q=10**18
obs=dict(pool=s['pool'],epoch=1,state_version=1,state_valid=True,state_received_ns=10**9,bbo_received_ns=10**9,provider_valid_until_ns=2*10**9,bid_e8=str(100*10**8),ask_e8=str(100*10**8),quantity=str(q),pool_bid_usdg='100200000',pool_ask_usdg='100300000')
def request(base,cash,**changes):
 return dict(ticker='NVDA',now_ns=10**9,inventory=dict(base=str(base*q),cash=str(cash)),observation=obs|changes)
requests=[request(3,500000000),request(2,600200000,pool_bid_usdg='100000000',pool_ask_usdg='100050000'),request(2,600200000,quantity=str(2*q),pool_bid_usdg='100000000',pool_ask_usdg='100050000'),request(3,500000000,pool_bid_usdg='99700000',pool_ask_usdg='99800000'),request(4,400200000,pool_bid_usdg='99950000',pool_ask_usdg='100000000'),request(0,800000000)]
with tempfile.TemporaryDirectory() as d:
 env=Path(d)/'inventory.env';env.write_text('\n'.join(f'INITIAL_STOCKS_{t}=3\nINITIAL_EXCHANGE_SHORT_{t}=3' for t in c['stocks']))
 r=subprocess.run(['cargo','run','--offline','--quiet','--example','metric_inventory_shadow','--','config/metric-inventory-shadow.json',str(env)],input='\n'.join(map(json.dumps,requests))+'\n',text=True,capture_output=True,check=True)
 rows=[json.loads(x) for x in r.stdout.splitlines()]
 assert rows[0]['sell']['opening'] and rows[0]['buy'] is None
 assert rows[1]['buy']['opening'] is False and rows[1]['sell'] is None
 assert rows[2]['buy'] is None  # no crossing baseline on close
 assert rows[3]['buy']['opening'] and rows[3]['sell'] is None
 assert rows[4]['sell']['opening'] is False and rows[4]['buy'] is None
 assert rows[5]['sell'] is None and rows[5]['exposure']['maximum_relative_short']==str(3*q)
 env.write_text('INITIAL_STOCKS_NVDA=\n')
 bad=subprocess.run(['target/debug/examples/metric_inventory_shadow','config/metric-inventory-shadow.json',str(env),'--audit'],capture_output=True)
 assert bad.returncode!=0
 print('PASS: short/open, buy/close, no baseline crossing, buy/open, sell/close, no oversell, blank baseline blocks startup')
