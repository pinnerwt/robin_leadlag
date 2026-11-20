import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from delegated_single_local import preview
from index4_local import PoolState
from index4_pool_state import load
from index4_observations import Ring,Observation
from v3_state import State
class DynamicRouteTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
  cls.chain=json.loads(Path('reports/amm/delegated-v3-chain-probe.json').read_text())
  cls.tx=cls.chain['tx'];cls.block=cls.tx['sequence'];cls.time=cls.tx['timestamp']
  cls.cases=next(c for c in json.loads(Path('reports/amm/delegated-single-callback-probe.json').read_text())['cases'] if c['tx']['tx']==cls.tx['tx'])
  cls.metadata={p['pool']:p for p in json.loads(Path('captures/startup-v9-quotes.json').read_text())['pools']}
  cls.curves={a:State.load(p) for a,p in cls.metadata.items()};cls.models={}
  for a,fee in zip(cls.cases['plan']['actions'][:2],(242,511)):
   storage=cls.seed['accounts'][a['target']]['storage'];v=int(storage['0x6'],16);tick=v>>160&0xffffff;tick=tick-(1<<24) if tick&(1<<23) else tick;center=(tick//a['spacing'])>>8
   curve=load(storage,effective_fee=fee,bitmap_words=range(center-2,center+3))
   # Explicit synthetic fee/observation fixture, never a live checkpoint.
   ring=Ring({0:Observation(cls.time,0,0,True)},0,1)
   cls.models[a['target']]=PoolState(curve,ring,0,600,{cls.block:fee},cls.block,cls.time,0)
   cls.metadata[a['target']]={'tokens':[a['currency0'],a['currency1']]}
 def test_composed_route_matches_verified_upstream_amounts(self):
  before=copy.deepcopy(self.curves);models=copy.deepcopy(self.models)
  r=preview(self.tx['data'],self.curves,self.metadata,self.curves,index4=models,block=self.block,timestamp=self.time)
  self.assertEqual(-r['fills'][0]['amount0'],self.chain['synthetic_first_output'])
  self.assertEqual(-r['fills'][1]['amount0'],self.chain['synthetic_second_output'])
  self.assertEqual(r['fills'][2]['amount0'],self.chain['synthetic_second_output'])
  self.assertEqual(self.curves,before)
  for p in models:self.assertEqual(models[p].curve,self.models[p].curve)
  self.assertFalse(r['post_hooks_evaluated']);self.assertFalse(r['execution_complete'])
 def test_missing_cache_aborts_without_partial_commit(self):
  models=copy.deepcopy(self.models);p=list(models)[1];models[p].fee_cache.clear();before=copy.deepcopy(models)
  with self.assertRaisesRegex(ValueError,'unknown block fee-cache'):preview(self.tx['data'],self.curves,self.metadata,self.curves,index4=models,block=self.block,timestamp=self.time)
  for p in models:self.assertEqual(models[p].curve,before[p].curve)
 def test_dynamic_fee_does_not_use_calldata_hint(self):
  models=copy.deepcopy(self.models);p=list(models)[0];models[p].fee_cache[self.block]=1000
  r=preview(self.tx['data'],self.curves,self.metadata,self.curves,index4=models,block=self.block,timestamp=self.time)
  self.assertEqual(r['fills'][0]['charged_fee'],1000)
  self.assertNotEqual(-r['fills'][0]['amount0'],self.chain['synthetic_first_output'])
