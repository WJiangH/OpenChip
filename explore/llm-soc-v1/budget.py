"""Architecture arithmetic only; not an ISS, workload implementation, or performance predictor."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
profile={'dim':64,'hidden':172,'layers':5,'qheads':8,'kvheads':4,'vocab':512,'group':64,'context_capacity':512,'forwards':48}
shapes=[(64,64),(32,64),(32,64),(64,64),(172,64),(172,64),(64,172)]*5+[(512,64)]
macs=sum(n*k for n,k in shapes);groups=sum(n*((k+63)//64) for n,k in shapes)
qbytes=macs;scale_bytes=groups*4;normbytes=(2*5+1)*64*4
model_payload=qbytes+scale_bytes+normbytes
header_directory=64+47*32
kv=2*5*512*32*4
activation_bytes=sum(((k+3)//4)*4 for n,k in shapes)
output_bytes=groups*4
traffic_floor=qbytes+activation_bytes+output_bytes
out={'status':'analytical-resource-and-lower-bounds-not-measured-DUT-performance','profile':profile,'macs_per_forward':macs,'groups_per_forward':groups,'weight_i8_bytes':qbytes,'scale_fp32_bytes':scale_bytes,'norm_fp32_bytes':normbytes,'model_payload_bytes':model_payload,'model_blob_bytes_before_any_optional_extra_alignment':model_payload+header_directory,'model_blob_header_directory_bytes':header_directory,'kv_capacity_bytes':kv,'kv_new_bytes_per_forward':2*5*32*4,'kv_populated_48_bytes':2*5*48*32*4,'host_original_nonkv_scratch_bytes':20832,'npu_group_output_bytes_per_forward':output_bytes,'npu_x_reads_per_forward_bytes':activation_bytes,'npu_traffic_floor_per_forward_bytes':traffic_floor,'axi_read_bytes_per_forward':qbytes+activation_bytes,'axi_write_bytes_per_forward':output_bytes,'ideal_parallel_read_write_cycles_floor':max((qbytes+activation_bytes+3)//4,(output_bytes+3)//4),'ideal_serialized_read_write_cycles_floor':(traffic_floor+3)//4,'full_run_macs':48*macs,'full_run_group_words':48*groups,'full_run_npu_traffic_floor_bytes':48*traffic_floor,'array_sweep':[{'mac_lanes':lanes,'ideal_compute_cycles_per_forward':sum(n*((k+lanes-1)//lanes) for n,k in shapes),'ideal_clock_hz':50000000,'raw_axi_bytes_per_cycle':4} for lanes in [1,4,8]],'sim_wallclock_sensitivity':[{'dut_cycles_assumption':cyc,'simulator_cycles_per_second_assumption':rate,'wall_seconds':cyc/rate} for cyc in [100000000,1000000000,10000000000] for rate in [100000,1000000,10000000]]}
prior=json.loads((root/'explore/llm-target-v0/estimates.json').read_text())
out['product_1_7b_w4_context2048_prior_analytic']=next(x for x in prior['rows'] if x['model']=='Qwen3-1.7B' and x['weight_bits']==4 and x['context']==2048)
path=Path(__file__).with_name('budget.json');path.write_text(json.dumps(out,indent=2)+'\n')
print('BUDGET PASS: MAC/forward=%d groups/forward=%d payload=%d KV512=%d traffic_floor=%d'%(macs,groups,model_payload,kv,traffic_floor))
assert (macs,groups,model_payload,kv)==(259328,4152,278752,655360)
