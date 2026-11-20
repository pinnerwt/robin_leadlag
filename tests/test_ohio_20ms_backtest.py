import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ohio_20ms_backtest import load_bbos,positive_leads

class ExpandedBacktestTests(unittest.TestCase):
 def test_kraken_ignores_late_updates_and_reconnect_snapshots(self):
  def row(recv,stamp,kind='update',bid='100'):
   return dict(kind='equity_bbo',ticker='META',venue='kraken',recv_ns=recv,exchange_timestamp='2026-11-19T03:34:00.'+stamp+'Z',message_type=kind,bid=bid,ask='102')
  rows=[row(10,'100','snapshot'),row(20,'200'),row(30,'150',bid='99'),row(40,'300','snapshot'),row(50,'250'),row(60,'250')]
  streams,q=load_bbos(rows,[('META','METABUSDT','kraken')],{'METABUSDT':5},0,100)
  self.assertEqual([r['mono_ns'] for r in streams[('META','kraken')]],[5,15,45,55])
  self.assertEqual(q['kraken_stale_source'],1);self.assertEqual(q['kraken_repeat_snapshot'],1)
 def test_refreshes_remain_and_late_sequence_is_excluded(self):
  row=dict(kind='equity_bbo',ticker='SPCX',venue='bybit',recv_ns=10,bid='100',ask='101')
  streams,q=load_bbos([row,dict(row,recv_ns=20),dict(row,recv_ns=30,is_late=True)],[('SPCX','SPCXBUSDT','bybit')],{'SPCXBUSDT':3},0,100)
  self.assertEqual([r['mono_ns'] for r in streams[('SPCX','bybit')]],[7,17]);self.assertEqual(q['late_sequence'],1)
 def test_selects_all_positive_source_leads_without_fold_cherry_picking(self):
  base=dict(ticker='META',x='kraken',y='robinhood_source',side='mid',folds={'10':[dict(status='ok',peak_ms=-1)]*10},gap5s_sensitivity=dict(peak_ms=-5))
  rows=[dict(base,full=dict(status='ok',peak_ms=n,boundary=False)) for n in [-1,0,1]]
  rows.append(dict(rows[-1],y='bybit'));rows.append(dict(rows[-2],side='ask'))
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'hy.json';p.write_text(json.dumps(dict(results=rows)));selected=positive_leads(p)
  self.assertEqual(len(selected),1);self.assertEqual(selected[0]['peak_ms'],1);self.assertEqual(selected[0]['positive_folds'],0)

if __name__=='__main__':unittest.main()
