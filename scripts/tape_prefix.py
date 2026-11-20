"""Stream a bounded RLLBIN prefix to JSONL without a large intermediate file."""
import argparse,json,subprocess,sys
from tape import read
p=argparse.ArgumentParser();p.add_argument('path');p.add_argument('--seconds',type=float,required=True);a=p.parse_args()
if a.seconds<=0:p.error('seconds must be positive')
process=subprocess.Popen(['zstd','-q','-dc','--',a.path],stdout=subprocess.PIPE)
bounded=False
try:
 for row in read(process.stdout):
  if row.get('mono_ns',0)>a.seconds*1e9:bounded=True;break
  print(json.dumps(row,separators=(',',':')))
except BrokenPipeError:
 bounded=True
 sys.stdout=open('/dev/null','w')
finally:
 process.stdout.close()
 if bounded:process.terminate()
 status=process.wait()
 if status and not bounded:raise RuntimeError(f'decompression failed: {status}')
