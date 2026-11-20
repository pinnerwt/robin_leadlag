"""Deterministic cross-language policy parity on exact-micro amounts; no network."""
import json,random,subprocess
from decimal import Decimal as D
from pathlib import Path
from metric_strategy import Policy,Inventory,decide
c=json.loads(Path('config/metric-execution-shadow.json').read_text());rng=random.Random(4663);rows=[];expected=[]
policy=Policy(D('500'),D('10'),delay_ns=20_000_000,max_bbo_age_ns=c['max_bbo_age_ns'])
for i in range(400):
 closing=i%2==1;qty=D('0.1');amount=D(100)+D(rng.randrange(-40,41))/100
 bid=amount-D('0.02');ask=amount+D('0.02');now=1_000_000_000;expiry=now+(19_999_999 if i%13==0 else 1_000_000_000)
 inv=Inventory(base=qty if closing else D(0),cash=D(0) if closing else D(500));side='sell' if closing else 'buy'
 q=dict(status='priced',state_valid=True,size_tokens=str(qty),bid_usdg=str(bid),ask_usdg=str(ask),available_ns=now,state_version=1)
 bbo=dict(bid='1000',ask='1000',available_ns=now)
 want=decide(policy,inv,side,qty,q,bbo,now,threshold_override=D('-10') if closing else D('10')) if expiry>=now+c['execution_budget_ns'] else None
 obs=dict(pool=c['pool'],epoch=1,state_version=1,state_valid=True,state_received_ns=now,bbo_received_ns=now,provider_valid_until_ns=expiry,bid_e8='100000000000',ask_e8='100000000000',quantity=str(int(qty*10**18)),pool_bid_usdg=str(int(bid*10**6)),pool_ask_usdg=str(int(ask*10**6)))
 rows.append(dict(now_ns=now,episode_open=closing,inventory=dict(base=str(int(inv.base*10**18)),cash=str(int(inv.cash*10**6))),observation=obs));expected.append(want)
p=subprocess.run(['target/debug/examples/metric_execution_shadow','config/metric-execution-shadow.json'],input=''.join(json.dumps(r)+'\n' for r in rows),text=True,capture_output=True,check=True)
results=[json.loads(l) for l in p.stdout.splitlines()];assert len(results)==len(rows)
for i,(row,want) in enumerate(zip(results,expected)):
 assert 'error' not in row,(i,row)
 got=row['intent'];assert (got is None)==(want is None),(i,got,want)
 if got:
  assert got['side']==want['side'];assert int(got['quantity'])==int(D(want['size_tokens'])*10**18);assert int(got['quote_usdg'])==int(D(want['amount_usdg'])*10**6)
print('400 Rust/Python admission, side, quantity and total-cost cases matched; expiry budget applied before both.')
