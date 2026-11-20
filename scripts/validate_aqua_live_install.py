"""Install same-block mainnet snapshots locally; no network or recorder startup."""
import copy,json,time
from pathlib import Path
from aqua_book import make_book,C9
seed=json.loads(Path('captures/aqua-v3-install-smoke.json').read_text())
subset=json.loads(Path('reports/amm/aqua-live-bootstrap.json').read_text())
if not seed['complete']:raise ValueError('V3 snapshot unfinished or invalid')
if seed['anchor']['hash']!=subset['anchor']['hash']:raise ValueError('live snapshots differ')
seed['aqua']=subset['aqua'];registry=subset['registry']
book=make_book(seed,registry,True)
case=json.loads(Path('tests/fixtures/c7_settlement.json').read_text())[0]
# Old calldata is a hypothetical input at this new state, not historical replay.
tx=dict(tx='hypothetical-local-c7',to=C9,data=case['calldata'],mono_ns=time.monotonic_ns(),recv_ns=time.time_ns())
start=time.perf_counter_ns();touched=book.proposal(tx);elapsed=time.perf_counter_ns()-start
if not touched:raise ValueError(book.unsupported.get(tx['tx'],'no transition'))
quotes=[q for pool in touched for q in book.quotes(pool,['0.02','0.1','0.123456789'],tx)]
assert all('bid' in q and 'ask' in q for q in quotes)
Path('captures/aqua-v3-installed-smoke.json').write_text(json.dumps(seed,indent=2)+'\n')
Path('reports/amm/aqua-live-install-validation.json').write_text(json.dumps(dict(anchor_hash=seed['anchor']['hash'],
 pools=len(seed['pools']),quoter_checks=len(seed['checks']),transition_compute_ns=elapsed,quotes=quotes,
 caveat='Actual same-block initialization; old calldata applied hypothetically. Single timing observation, not latency distribution or historical parity.'),indent=2)+'\n')
print(json.dumps(dict(pools=len(seed['pools']),checks=len(seed['checks']),local_transition_ns=elapsed,quote_sizes=len(quotes))))
