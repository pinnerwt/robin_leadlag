"""Offline checkpoint integration checks for the research Metric reducer."""
import json
import subprocess
from pathlib import Path

seed='captures/startup-v9-dependencies.json'
header=json.loads(Path(seed).read_text())['parent_header']
root='0xcc1ae96cd8479f896a8dba85eab09a694b929b6c'
base=dict(header=header,pool='0xaf2640f82a499abfcf143fec309f1d8953b4a3ab',
          zero=True,amount=str(10**16),sender=root,recipient=root,commit=False)
requests=[base,dict(base,amount=str(10**18),commit=True),base,
          dict(base,commit=True),base,dict(base,zero=False,amount='1000000')]
out=subprocess.check_output(['target/release/examples/metric_transition',seed],
                            input=''.join(json.dumps(r)+'\n' for r in requests),text=True)
responses=[json.loads(line) for line in out.splitlines()]
assert len(responses)==len(requests)
def canonical(value):
    result=dict(value['result'])
    result['storage_changes']=sorted(result['storage_changes'],key=lambda v:(v['address'],v['slot']))
    return result
assert 'partial input fill' in responses[1]['error']
assert canonical(responses[0])==canonical(responses[2]),'failed candidate leaked state'
assert responses[3]['result']['committed']
a=canonical(responses[0]);b=canonical(responses[4])
assert a['storage_changes']!=b['storage_changes'],'commit did not alter next transition'
assert responses[5]['result']['amount1']=='1000000'
report=dict(purpose='Offline archived-checkpoint transition integration, not historical swap parity',
            checks=['buy and sell exact-input simulation','failed candidate rollback',
                    'dry-run isolation','successful commit affects next transition'],
            cases=[dict(request=r,response=v) for r,v in zip(requests,responses)])
Path('reports/amm/metric-transition-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print('4 integration checks passed; 6 sequential requests, zero network')
