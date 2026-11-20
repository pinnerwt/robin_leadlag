"""Compare local checkpoint curve math against actual manager swap returns."""
import json
from pathlib import Path
from routera3d_v4 import reverse_intent,MANAGER
from v4_pool_state import load

seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
report=json.loads(Path('reports/amm/routera3d-index6-settlement-validation.json').read_text())
records=[];fixture=None
for c in report['cases']:
    exponent=c['exponent'];doc=json.loads(Path(f'reports/amm/routera3d-index6-probe-{exponent}-settlement.json').read_text())
    intent=reverse_intent(doc['transaction']['data'],1,10**12,hook_fee_ppm=40)
    # Initialization deliberately loads a bounded bitmap region. Leaving it
    # raises unknown-state errors rather than inferring empty liquidity.
    state=load(seed['accounts'][MANAGER]['storage'],intent,effective_lp_fee=40,bitmap_words=range(-788,-784))
    if fixture is None:fixture=state.__dict__.copy()
    result=state.swap(False,-intent['amount'],intent['limit'])
    assert result['amount0']==-c['output_native_raw'] and result['amount1']==c['input_usdg_raw'],(c,result)
    base=int(doc['slot'],16)
    writes=[w for w in doc['result']['storage_writes'] if w['address']==MANAGER and int(w['slot'],16)==base]
    assert len(writes)==1
    packed=int(writes[0]['value'],16)
    assert result['sqrt']==packed&((1<<160)-1)
    tick=(packed>>160)&((1<<24)-1);tick=tick-(1<<24) if tick>>23 else tick
    assert result['tick']==tick
    records.append(dict(exponent=exponent,amount=-intent['amount'],limit=intent['limit'],result=result))
Path('reports/amm/routera3d-v4-math-validation.json').write_text(json.dumps(dict(matches=len(records),records=records,
    caveat='Independent integer curve replay from archived pool storage matches actual manager amount/sqrt/tick in four controlled experiments. Hook branch fixed to observed zero-delta 40-ppm override. Not historical root parity or general hook reconstruction.'),indent=2)+'\n')
Path('tests/fixtures/routera3d_v4_math.json').write_text(json.dumps(dict(state=fixture,cases=records),indent=2)+'\n')
print(f'{len(records)} local V4 amount/sqrt/tick matches')
