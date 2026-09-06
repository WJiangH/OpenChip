"""Document-schema and arithmetic consistency audit; no hardware or numeric reference implementation."""
from pathlib import Path
import json,re
root=Path(__file__).resolve().parents[2];d=root/'docs/spec/llm-soc-v1'
c=json.loads((d/'contract.json').read_text());b=json.loads((root/'explore/llm-soc-v1/budget.json').read_text());w=json.loads((root/'workloads/llm-soc-v1/profile.json').read_text())
blocks={x['id'] for x in c['blocks']};assert len(blocks)==len(c['blocks'])
ids=[x['id'] for x in c['connections']];assert len(ids)==len(set(ids))
for x in c['connections']:
 assert x['source'] in blocks and x['target'] in blocks,(x['id'],'endpoint')
 assert x['protocol'] in c['protocols'],x
 for k,v in c['protocols'][x['protocol']]['signals'].items(): assert (v['width'] if isinstance(v,dict) else v)>0,(x['id'],k)
regions=sorted(c['address_regions'],key=lambda q:q['base'])
for i,x in enumerate(regions):
 assert x['base']+x['size']==x['end_exclusive'] and x['size']>0
 if i: assert regions[i-1]['end_exclusive']<=x['base'],(regions[i-1]['id'],x['id'])
for r in c['csr_registers']:
 area=next(x for x in regions if x['id']==r['block']);assert r['address']==area['base']+r['offset'] and r['offset']%4==0 and r['offset']<area['size']
 bits=[]
 for f in r['fields']:
  assert 0<=f['lsb']<=f['msb']<32
  bits += list(range(f['lsb'],f['msb']+1))
 assert len(bits)==len(set(bits)),r
assert len({x['address'] for x in c['csr_registers']})==len(c['csr_registers'])
assert set(c['protocols']['axi4_lite']['signals'])==set('AWVALID AWREADY AWADDR AWPROT WVALID WREADY WDATA WSTRB BVALID BREADY BRESP ARVALID ARREADY ARADDR ARPROT RVALID RREADY RDATA RRESP'.split())
req=[]
for p in d.glob('*.md'):
 req+=re.findall(r'\*\*([A-Z]+-\d+)(?: \(S1\))?:\*\*',p.read_text())
assert len(req)==len(set(req))
assert set(req)=={x['id'] for x in c['requirements']}
trace=(d/'traceability.md').read_text()
for x in req:assert '|'+x+'|' in trace or '| '+x+' |' in trace,x
assert len(w['prompt_ids'])==32 and len(w['expected_generated_ids'])==16
assert all(0<=x<512 for x in w['prompt_ids']+w['expected_generated_ids'])
assert b['model_payload_bytes']==278752 and b['kv_capacity_bytes']==655360
assert b['full_run_macs']==12447744 and b['full_run_group_words']==199296
assert b['ideal_parallel_read_write_cycles_floor']==65543 and b['ideal_serialized_read_write_cycles_floor']==69695
print('CONTRACT AUDIT PASS: blocks=%d connections=%d regions=%d CSR=%d requirements=%d Lite_signals=19; budget/profile consistent'%(len(blocks),len(ids),len(regions),len(c['csr_registers']),len(req)))
print('NOT RUN: firmware build, RTL lint/simulation/coverage/ISA/formal/synthesis/timing, S1, FPGA, physical signoff')
