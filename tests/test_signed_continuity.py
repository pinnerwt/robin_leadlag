"""Offline integration using retained mainnet diagnostic witnesses."""
import json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class SignedContinuity(unittest.TestCase):
 def test_one_load_six_transactions(self):
  with tempfile.TemporaryDirectory() as d:
   report=Path(d)/'report.json'
   p=subprocess.run(['python3',str(ROOT/'scripts/replay_continuity_fixtures.py'),'--fixtures',str(ROOT/'captures/signed-covered-fixtures.json'),'--seed-output',str(Path(d)/'seed.json'),'--output',str(report)],cwd=ROOT,text=True,capture_output=True)
   self.assertEqual(p.returncode,0,p.stderr+p.stdout)
   r=json.loads(report.read_text());self.assertTrue(r['matched']);self.assertEqual(r['executed_transactions'],6);self.assertEqual(r['continuous_checkpoint_loads'],1);self.assertFalse(r['production_ready'])
