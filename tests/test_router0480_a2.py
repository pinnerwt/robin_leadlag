import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_guards import inspect,evaluate
class A2Test(unittest.TestCase):
 def test_original_actual_getters_and_comparisons(self):
  r=json.loads(Path('reports/amm/router0480-a2.json').read_text());p=inspect(r['tx']['data']);self.assertEqual([g['opcode'] for g in p['guards']],[162,162,161]);prices={}
  returns=[x for x in r['result']['execution_returns'] if x['selector']=='0xe76c01e4'];comp=[x for x in r['result']['control_ops'] if x['pc'] in (18925,20947)]
  self.assertEqual(len(returns),2)
  for g,x,c in zip(p['guards'],returns,comp):
   self.assertEqual(g['getter'],x['selector']);self.assertEqual(g['pool'],x['to']);prices[g['pool']]=int(x['output'][2:66],16);self.assertEqual(prices[g['pool']],int(c['a']));self.assertEqual(g['limit'],int(c['b']))
  self.assertEqual(evaluate(p,prices),dict(skip=True,failed_guard=1));self.assertTrue(r['result']['execution_success']);self.assertFalse(r['result']['calls'])
 def test_equal_and_missing_price(self):
  r=json.loads(Path('reports/amm/router0480-a2.json').read_text());p=inspect(r['tx']['data']);prices={g['pool']:g['limit'] for g in p['guards']};self.assertFalse(evaluate(p,prices)['skip'])
  prices.pop(p['guards'][0]['pool'])
  with self.assertRaises(ValueError):evaluate(p,prices)
 def test_actual_algebra_swap_prefixes_and_route(self):
  from router0480_first_swap import intent
  from router0480_route import inspect as route
  r=json.loads(Path('reports/amm/router0480-a2-nested.json').read_text());self.assertEqual(len(r['swaps']),3);self.assertEqual(r['synthetic_registrations'],[])
  for i,s in enumerate(r['swaps'],3):
   p=intent(r['tx']['data'],i);c=s['call'];d=bytes.fromhex(c['data'][10:]);self.assertEqual(p['pool'],c['to']);self.assertEqual(p['amount'],int.from_bytes(d[64:96],'big',signed=True));self.assertEqual(p['zero'],bool(int.from_bytes(d[32:64],'big')));self.assertEqual(p['limit'],int.from_bytes(d[96:128],'big'))
   if i>3:self.assertEqual(p['swap_opcode'],4);self.assertIsNone(p['callback_profile']);self.assertEqual(s['callback'][:10],'0x2c8958f6')
  original=json.loads(Path('reports/amm/router0480-a2.json').read_text());p=route(original['tx']['data']);self.assertEqual(p['pools'],[s['call']['to'] for s in r['swaps']]);self.assertFalse(p['execution_complete'])
