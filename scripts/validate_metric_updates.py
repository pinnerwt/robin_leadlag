"""Captured oracle calldata changes the same local state used for quoting."""
import json
import subprocess
from pathlib import Path
seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
updates=json.loads(Path('tests/fixtures/metric_oracle_updates.json').read_text())
updates.append(json.loads(Path('tests/fixtures/metric_weth_oracle_update.json').read_text()))
assert [r['sequence'] for r in updates]==sorted(r['sequence'] for r in updates)
root='0xcc1ae96cd8479f896a8dba85eab09a694b929b6c'
quote=dict(pool='0xaf2640f82a499abfcf143fec309f1d8953b4a3ab',zero=True,
           amount=str(10**16),sender=root,recipient=root,commit=False,header=seed['parent_header'])
requests=[quote]
for tx in updates:
    header=dict(l1BlockNumber=hex(tx['l1_block']),timestamp=hex(tx['timestamp']))
    requests.append(dict(kind='oracle_update',header=header,transaction={k:tx[k] for k in ('to','from','data')},commit=True))
    requests.append(dict(quote,header=header))
out=subprocess.check_output(['target/release/examples/metric_transition','captures/startup-v9-dependencies.json'],
                            input=''.join(json.dumps(r)+'\n' for r in requests),text=True)
responses=[json.loads(line) for line in out.splitlines()]
assert len(responses)==len(requests)
for index in (1,3,5):assert responses[index]['result']['changed_slots']>0
for index in (0,6):assert responses[index]['result']['committed'] is False
assert all('provider failed' in responses[i]['error'] for i in (2,4)), 'unrelated feed updates must not revive WETH quotes'
prices=[responses[i]['result']['simulation_call']['data'][330:522] for i in (0,6)]
assert len(set(prices))>1,'oracle update did not affect these quotes'
Path('reports/amm/metric-oracle-quote-validation.json').write_text(json.dumps(dict(
 purpose='Captured update calldata at supplied headers against archived seed, not full historical timeline',
 cases=[dict(request=q,response=r) for q,r in zip(requests,responses)],provider_prices_changed=True),indent=2)+'\n')
print('both oracle updates committed and local provider prices changed')

from cc1a_state_bridge import Bridge,RejectedTransition
v3=json.loads(Path('captures/startup-v9-quotes.json').read_text())
with Bridge(v3,'captures/startup-v9-dependencies.json') as bridge:
    for tx in updates:assert bridge.update_oracle(tx)['changed_slots']>0
    assert bridge.header['timestamp']==hex(updates[-1]['timestamp'])
    invalid=dict(updates[-1],to='0x'+'11'*20)
    try:bridge.update_oracle(invalid)
    except RejectedTransition:pass
    else:raise AssertionError('unsupported oracle accepted')
    assert not bridge.valid
print('bridge applies updates and invalidates after an unapplied update')
