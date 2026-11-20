import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from delegated_spcx_cycle import preview,UPSTREAM,RECORDED,POOL_ID
from v3_state import State
class CycleTest(unittest.TestCase):
 def test_three_curves_and_actual_v4_return(self):
  f=json.loads(Path('reports/amm/delegated-spcx-cycle-preview.json').read_text())
  curves={a:State.load(s) for a,s in f['curves'].items()};before=copy.deepcopy(curves)
  result=preview(f['strategy'],curves,hook_state=f['hook_state'],hook_config=f['hook_config'],block=f['block'])
  refs=['delegated-upstream-curve-probe','delegated-two-pool-curve-probe','delegated-v4-curve-probe']
  for fill,name in zip(result['fills'],refs):
   expected=json.loads(Path('reports/amm/'+name+'.json').read_text())['expected']
   self.assertEqual({k:v for k,v in fill.items() if k!='pool'},expected)
  v4=json.loads(Path('reports/amm/delegated-v4-curve-probe.json').read_text())
  call=next(x for x in v4['result']['execution_returns'] if x['selector']=='0xf3cd914c' and x['result']=='Return')
  self.assertEqual(result['output_native'],int(call['output'],16)>>128)
  self.assertEqual(result['native_difference'],-525008791357228);self.assertEqual(curves,before)
  bad=copy.deepcopy(f['strategy']);bad['actions'][3]['hook']='0x'+'11'*20
  with self.assertRaises(ValueError):preview(bad,curves,hook_state=f['hook_state'],hook_config=f['hook_config'],block=f['block'])
  self.assertEqual(curves,before)
