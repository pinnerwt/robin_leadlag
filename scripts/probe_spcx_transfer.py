"""Token accounting intervention with explicit synthetic eligibility/balances."""
import json,subprocess,tempfile,argparse
from pathlib import Path
BEACON='0xe10b6f6b275de231345c20d14ab812db62151b00'
IMPL='0xb35490d6f9163de4f80d88dc75c3516eb64c5ae2'
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--patch',default='{}');ap.add_argument('--output',default='reports/amm/delegated-spcx-accounting-probe.json');args=ap.parse_args();patch=json.loads(args.patch)
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
 source=json.loads(Path('reports/amm/delegated-spcx-transfer-probe.json').read_text());tx=source['transaction']
 seed.update(execute_targets=[BEACON],delegate_targets=[IMPL],trace_execution=True,trace_hashes=True)
 for address,slots in patch.items():seed['accounts'][address]['storage'].update(slots)
 with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
  Path(tmp.name).write_text(json.dumps(seed))
  result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
 Path(args.output).write_text(json.dumps(dict(transaction=tx,synthetic_storage=patch,result=result,caveat='Explicit token eligibility/balance intervention; not historical account status.'),indent=2)+'\n')
 print(result['error'],result['output'],result['storage_writes'])
 print(result['hash_preimages'][-4:])
if __name__=='__main__':main()
