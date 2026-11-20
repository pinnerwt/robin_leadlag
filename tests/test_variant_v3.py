import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from settler_funded_v3 import intent
class VariantV3Test(unittest.TestCase):
 def test_funded_action_matches_actual_settler_call(self):
  entry=json.loads(Path('reports/amm/batch-unpinned-plans.json').read_text())['transactions'][1]
  imm=json.loads(Path('reports/amm/variant-v3-immutables.json').read_text())
  pool=dict(pool='0xf55045c021949b202a5d10451b2ffa01561c5f55',tokens=['0x'+imm[k]['output'][-40:] for k in ('token0()','token1()')],fee=int(imm['fee()']['output'],16),spacing=int(imm['tickSpacing()']['output'],16))
  action=entry['plan']['actions'][0]['data'];a=intent(action,[pool]);tx=json.loads(Path('reports/amm/variant-v3-settled.json').read_text())['tx'];d=bytes.fromhex(tx['data'][10:])
  self.assertEqual(a['pool'],tx['to']);self.assertEqual(a['amount'],int.from_bytes(d[64:96],'big',signed=True));self.assertEqual(a['limit'],int.from_bytes(d[96:128],'big'));self.assertEqual(a['zero'],bool(int.from_bytes(d[32:64],'big')))
  with self.assertRaises(ValueError):intent(action+'00',[pool])
  with self.assertRaises(ValueError):intent(action,[])
 def test_independent_curve_parity(self):
  from bootstrap_state import mapping
  from v3_state import State
  r=json.loads(Path('reports/amm/variant-v3-settled.json').read_text());self.assertTrue(r['result']['execution_success']);self.assertTrue(r['anchor_verified'])
  s={int(k,16):int(v,16) for k,v in r['seed']['accounts'][r['tx']['to']]['storage'].items()};slot=s[0];tick=(slot>>160)&((1<<24)-1);bitmap={2:s[int(mapping(2,6),16)]}
  curve=State(slot&((1<<160)-1),tick,s[4],10000,200,bitmap,{})
  d=bytes.fromhex(r['tx']['data'][10:]);a=int.from_bytes(d[64:96],'big');fill=curve.swap(False,a,int.from_bytes(d[96:128],'big'));out=bytes.fromhex(r['result']['output'][2:])
  self.assertEqual([fill['amount0'],fill['amount1']],[int.from_bytes(out[i:i+32],'big',signed=True) for i in (0,32)]);self.assertEqual(fill['unfilled'],0)
  writes={int(w['slot'],16):int(w['value'],16) for w in r['result']['storage_writes']};self.assertEqual(fill['sqrt'],writes[0]&((1<<160)-1));self.assertEqual(fill['tick'],(writes[0]>>160)&((1<<24)-1))
