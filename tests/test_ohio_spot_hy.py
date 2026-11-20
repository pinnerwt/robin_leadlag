import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ohio_spot_hy import clean,increments,scan,rfc_ns
class HyTest(unittest.TestCase):
 def test_known_positive_lag(self):
  rng=np.random.default_rng(11);t=np.cumsum(rng.integers(50,150,3000));price=100*np.exp(np.cumsum(rng.normal(0,.0001,len(t))))
  x,xb=clean(np.column_stack((t,price)));y,yb=clean(np.column_stack((t+200,price)))
  result=scan(x,xb,y,yb,t[0]+200,t[-1],limit=1000)
  self.assertLessEqual(abs(result['peak_ms']-200),50)
  reverse=scan(y,yb,x,xb,t[0]+200,t[-1],limit=1000)
  self.assertLessEqual(abs(reverse['peak_ms']+200),50)
 def test_vectorized_matches_interval_overlap(self):
  x,xb=clean(np.array([[0,100],[100,101],[220,99],[400,102],[700,101],[1000,103]],float))
  y,yb=clean(np.array([[20,101],[180,99],[350,102],[650,101],[800,103],[980,104]],float))
  result=scan(x,xb,y,yb,0,1000,step=50,limit=100)
  xr=increments(x,xb,0,1000,15000);yr=increments(y,yb,100,900,15000)
  norm=np.sqrt(sum(z*z for _,_,z in xr)*sum(z*z for _,_,z in yr))
  for lag,value in result['curve']:
   direct=sum(dx*dy for a,b,dx in xr for c,d,dy in yr if a<d-lag and b>c-lag)/norm
   self.assertAlmostEqual(value,direct,places=12)
 def test_requested_fine_grid(self):
  x,xb=clean(np.array([[0,100],[10,101],[30,99],[80,102],[150,103],[200,100],[250,102],[400,101]],float))
  result=scan(x,xb,x,xb,0,400,step=2,limit=100,min_lag=1)
  self.assertEqual([lag for lag,_ in result['curve']],sorted({0,-100,100,*range(1,100,2),*range(-99,0,2)}))
 def test_gap_break(self):
  p,bad=clean(np.array([[0,100],[100,101],[150,np.nan],[200,200],[300,201]],float))
  r=increments(p,bad,0,300,5000)
  self.assertEqual(r[:,0].tolist(),[0,200])
 def test_source_timestamp(self):
  self.assertEqual(rfc_ns('2026-11-19T14:30:00.123456789Z'),1795098600123456789)
if __name__=='__main__':unittest.main()
