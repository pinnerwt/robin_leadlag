import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router7627_reverse import first_leg
from variant_v3_checkpoint import load
class ReverseTest(unittest.TestCase):
 def test_actual_reverse_first_leg(self):
  report=json.loads(Path('reports/amm/router7627-local-getters-shift--5-inventory-1000000000000000000-unlock.json').read_text())
  for row in report['cases']:
   r=row['result'];self.assertIsNone(r['error']);c=r['calls'][0];b=bytes.fromhex(c['data'][10:]);limit=int.from_bytes(b[96:128],'big');p=first_leg(limit);self.assertEqual(p['data'],c['data']);self.assertEqual(p['pool'],c['to']);self.assertFalse(r['execution_success'])
 def test_actual_observation_state_gap(self):
  report=json.loads(Path('reports/amm/router7627-local-getters-shift--5-inventory-1000000000000000000-unlock-v3.json').read_text())
  for row in report['cases']:
   r=row['result'];self.assertIn('unknown slot',r['error']);self.assertTrue(r['error'].endswith('0x202b'));self.assertIsNone(r['execution_success'])

 def test_observation_interventions_match_numeric_curve(self):
  pool='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca';seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());state=load(seed['accounts'][pool]['storage'],100,1);fill=state.swap(True,10**19,int('2ccb972061e5a794aa5ce',16));self.assertGreater(fill['unfilled'],0);self.assertLess(fill['amount0'],10**19)
  for cumulative in (0,123456):
   report=json.loads(Path(f'reports/amm/router7627-local-getters-shift--5-inventory-1000000000000000000-unlock-v3-obs-{cumulative}.json').read_text())
   for row in report['cases']:
    self.assertEqual({x['slot'] for x in row['synthetic_observations']},{'0x202b','0x202c'});r=row['result'];self.assertIsNone(r['error']);c=r['calls'][0];self.assertEqual(c['data'][:10],'0xa9059cbb');self.assertEqual(c['to'],'0x5fc5360d0400a0fd4f2af552add042d716f1d168');self.assertEqual(int(c['data'][-64:],16),-fill['amount1']);self.assertFalse(r['execution_success'])

 def test_reverse_callback_and_second_leg_match_local_curve(self):
  from router7627_reverse import second_leg
  seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
  state=load(seed['accounts']['0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca']['storage'],100,1)
  fill=state.swap(True,10**19,int('2ccb972061e5a794aa5ce',16))
  report=json.loads(Path('reports/amm/router7627-local-getters-shift--5-inventory-1000000000000000000-unlock-v3-transfer-obs-0-reverse-balance.json').read_text())
  for row in report['cases']:
   result=row['result'];self.assertIsNone(result['error'])
   callback=next(c for c in result['execution_calls'] if c['data'].startswith('0xfa461e33'))
   raw=bytes.fromhex(callback['data'][10:])
   deltas=[int.from_bytes(raw[i:i+32],'big',signed=True) for i in (0,32)]
   self.assertEqual(deltas,[fill['amount0'],fill['amount1']])
   predicted=second_leg(*deltas);actual=result['calls'][0]
   self.assertEqual(predicted['to'],actual['to']);self.assertEqual(predicted['data'],actual['data'])
   self.assertFalse(result['execution_success']);self.assertFalse(predicted['execution_complete'])
  for pair in [(0,-1),(1,0),(-1,1),(True,-1)]:
   with self.assertRaises(ValueError):second_leg(*pair)

 def test_real_v4_second_leg_matches_local_curve(self):
  from v4_pool_state import load as load_v4
  seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
  manager='0x8366a39cc670b4001a1121b8f6a443a643e40951'
  key=dict(currency0='0x'+'00'*20,currency1='0x5fc5360d0400a0fd4f2af552add042d716f1d168',fee=0x800000,tick_spacing=1,hooks='0x987e330f00b79864a07fe81dfac344d0078abcc0')
  state=load_v4(seed['accounts'][manager]['storage'],key,effective_lp_fee=40,bitmap_words=range(-788,-784))
  from router7627_second_leg import LIMIT
  expected=state.swap(False,4548949483,LIMIT)
  report=json.loads(Path('reports/amm/router7627-local-getters-shift--5-inventory-1000000000000000000-unlock-v3-transfer-obs-0-reverse-balance-v4.json').read_text())
  for row in report['cases']:
   result=row['result'];self.assertIsNone(result['error'])
   returned=[c for c in result['execution_returns'] if c['selector']=='0xf3cd914c' and c['result']=='Return'];self.assertEqual(len(returned),1)
   raw=bytes.fromhex(returned[0]['output'][2:]);self.assertEqual([int.from_bytes(raw[i:i+16],'big',signed=True) for i in (0,16)],[-expected['amount0'],-expected['amount1']])
   hooks=[c for c in result['execution_returns'] if c['selector']=='0x575e24b4' and c['result']=='Return'];self.assertTrue(hooks)
   for c in hooks:
    self.assertEqual(int(c['output'][66:130],16),0);self.assertEqual(int(c['output'][-64:],16),0x400028)
   writes=[w for w in result['storage_writes'] if w['address']==manager and w['slot']=='0xa652248898f7392773fb86e84bf1ef4cf17b449600f2d309595c039285782ad8'];self.assertEqual(len(writes),1);self.assertEqual(int(writes[0]['value'],16)&((1<<160)-1),expected['sqrt'])
   self.assertFalse(result['execution_success'])
