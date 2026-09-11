"""Public-pin-only independent host, responder and trace execution."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import cocotb
from cocotb.triggers import Timer
from checker import Checker,FIELDS,initial_image,require
from responder import Responder
from host_checker import HostChecker
CHANNEL={'ar':'read_addr','r':'read_data','aw':'write_addr','w':'write_data','b':'write_resp'}
TIE={'io_irq':0,'io_timer_irq':0,'io_software_irq':0,'io_te':0,'io_dm_req_valid':0,'io_dm_req_bits_address':0,'io_dm_req_bits_data':0,'io_dm_req_bits_op':0,'io_dm_rsp_ready':1}
class Harness:
    def __init__(self,dut,config,out):
        self.d=dut; self.config=config; self.out=out; self.cycle=0
        image,self.image_info=initial_image(config['elf'],config['salt'],config['run_id'])
        (out/'initial-image.bin').write_bytes(image)
        require(self.image_info['elf_sha256']==config['elf_sha256'],'CNEM-01 ELF hash')
        require(self.image_info['entry']==config['entry'],'CNEM-05 ELF entry')
        require(config['entry']//16!=config['kernel']//16,'CNEM-05 distinct fetch lines')
        require(config['review_verdict']=='APPROVED','CNEM-29 software review missing')
        self.boot_check=HostChecker(config['entry']); self.check=Checker(image,config); self.resp=Responder(image,config['schedule'],config['seed'])
        self.trace=gzip.open(out/'trace.jsonl.gz','wt'); self.host=[]; self.bindings=[]
        self.handles={}
        for port in ('master','slave'):
            for ch,fields in FIELDS.items():
                for name,width in {'valid':1,'ready':1,**{'bits_'+k:v for k,v in fields.items()}}.items():
                    full=f'io_axi_{port}_{CHANNEL[ch]}_{name}'; h=getattr(dut,full)
                    require(len(h)==width,'CNEM-03 width '+full)
                    request=ch in ('ar','aw','w')
                    producer_dut=(port=='master')==request
                    direction='output' if producer_dut != (name=='ready') else 'input'
                    self.handles[full]=h; self.bindings.append({'name':full,'width':width,'contract_direction':direction})
        widths={'io_aclk':1,'io_aresetn':1,'io_boot_addr':32,'io_halted':1,'io_fault':1,'io_wfi':1,
                'io_dm_req_ready':1,'io_dm_rsp_valid':1,'io_dm_rsp_bits_data':32,'io_dm_rsp_bits_op':2}
        widths.update({name:32 if name.endswith(('address','data')) else 2 if name.endswith('_op') else 1 for name in TIE})
        for name,width in widths.items():
            require(len(getattr(dut,name))==width,'CNEM-03 scalar/DM width '+name)
            self.bindings.append({'name':name,'width':width})
        for name,value in TIE.items(): getattr(dut,name).value=value
        dut.io_aclk.value=0; dut.io_aresetn.value=0; dut.io_boot_addr.value=config['entry']
        for ch in ('ar','aw','w'):
            self.set('slave',ch,'valid',0)
            for k in FIELDS[ch]: self.set('slave',ch,'bits_'+k,0)
        self.set('slave','r','ready',1); self.set('slave','b','ready',1)
    def set(self,port,ch,name,value): self.handles[f'io_axi_{port}_{CHANNEL[ch]}_{name}'].value=value
    def get(self,port,ch,name): return int(self.handles[f'io_axi_{port}_{CHANNEL[ch]}_{name}'].value)
    def sample(self,port):
        return {ch:{'valid':self.get(port,ch,'valid'),'ready':self.get(port,ch,'ready'),'p':{k:self.get(port,ch,'bits_'+k) for k in fields}} for ch,fields in FIELDS.items()}
    async def tick(self):
        self.d.io_aclk.value=0
        output=self.resp.outputs(self.cycle+1)
        for ch in ('ar','aw','w'): self.set('master',ch,'ready',output[ch]['ready'])
        for ch in ('r','b'):
            self.set('master',ch,'valid',output[ch]['valid'])
            for k,v in output[ch]['p'].items(): self.set('master',ch,'bits_'+k,v)
        await Timer(5,unit='ns')
        master=self.sample('master'); slave=self.sample('slave')
        self.d.io_aclk.value=1; self.cycle+=1
        # Payload was sampled just before the rising edge; status after sequential update.
        await Timer(1,unit='ns')
        status={k:int(getattr(self.d,'io_'+k).value) for k in ('halted','fault','wfi')}
        reset=int(self.d.io_aresetn.value)
        for name,value in TIE.items(): require(int(getattr(self.d,name).value)==value,'CNEM-04 tieoff '+name)
        self.trace.write(json.dumps({'cycle':self.cycle,'reset_n':reset,'boot_addr':int(self.d.io_boot_addr.value),'master':master,'slave':slave,'status':status},separators=(',',':'))+'\n')
        self.boot_check.process(self.cycle,reset,int(self.d.io_boot_addr.value),slave,self.resp.locked)
        if reset:
            self.check.process(self.cycle,master,status)
            self.resp.advance(self.cycle,master)
        await Timer(4,unit='ns')
        self.d.io_aclk.value=0
        return slave
    async def clocks(self,n):
        for _ in range(n): await self.tick()
    async def csr(self,address,value=None):
        require(self.check.release is None,'CNEM-10 host access during execution')
        ch='ar' if value is None else 'aw'
        p={'addr':address,'id':0,'len':0,'size':2,'burst':1,'lock':0,'cache':0,'prot':0,'qos':0,'region':0}
        self.set('slave',ch,'valid',1)
        for k,v in p.items(): self.set('slave',ch,'bits_'+k,v)
        if value is not None:
            self.set('slave','w','valid',1)
            for k,v in {'data':value<<(8*(address&15)),'strb':15<<(address&15),'last':1}.items(): self.set('slave','w','bits_'+k,v)
        addr_done=False; data_done=value is None
        start=self.cycle
        while self.cycle<start+256:
            s=await self.tick()
            if s[ch]['valid'] and s[ch]['ready']: addr_done=True; self.set('slave',ch,'valid',0)
            if value is not None and s['w']['valid'] and s['w']['ready']: data_done=True; self.set('slave','w','valid',0)
            rch='r' if value is None else 'b'
            if s[rch]['valid'] and s[rch]['ready']:
                q=s[rch]['p']; require(addr_done and data_done and q['id']==0 and q['resp']==0,'CNEM-10 CSR response')
                if value is None: require(q['last']==1,'host RLAST')
                got=(q.get('data',0)>>(8*(address&15)))&0xffffffff
                self.host.append({'address':address,'value':value,'result':got,'start':start,'response_cycle':self.cycle})
                return got
        raise AssertionError('CNEM-10 host CSR timeout')
    async def run(self):
        await self.clocks(10)
        self.boot_check.reset_transition(self.cycle,'falling')
        self.d.io_aresetn.value=1
        await self.clocks(10)
        require(await self.csr(0x200000)==3,'CNEM-10 RESET_CONTROL readback')
        require(await self.csr(0x200004)==self.config['entry'],'CNEM-10 boot capture')
        await self.csr(0x200004,self.config['entry'])
        require(await self.csr(0x200004)==self.config['entry'],'CNEM-10 PC readback')
        self.resp.locked=True
        self.image_info['locked_cycle']=self.cycle
        await self.csr(0x200000,1); await self.clocks(10)
        await self.csr(0x200000,0); self.check.release=self.cycle
        while self.check.halt is None or self.cycle<self.check.halt+32: await self.tick()
        self.boot_check.finish()
        require(self.boot_check.release==self.check.release,'CNEM-10 release observer mismatch')
        require(self.resp.memory==self.check.mem,'CNEM-15 separate responder/scoreboard final equality')
        if self.config['schedule']=='P1':
            for channel in ('r','b'):
                require(any(self.resp.counts[channel+'_delay_'+str(n)] for n in range(2,16)),'CNEM-19 P1 delayed '+channel+' NOT_EXERCISED')
    def close(self,verdict,error=None):
        self.trace.close()
        (self.out/'final-memory.bin').write_bytes(self.resp.memory)
        result={'verdict':verdict,'error':error,'config':self.config,'image':self.image_info,'bindings':self.bindings,'host_transactions':self.host,'scoreboard':self.check.summary(),'schedule_counts':dict(self.resp.counts),'executed_cycles':self.cycle,'checked_scope':'positive continuous protocol, byte scoreboard, full terminal; negatives/reset NOT_RUN'}
        (self.out/'verdict.json').write_text(json.dumps(result,indent=2)+'\n')
@cocotb.test()
async def external_memory(dut):
    config=json.loads(Path(os.environ['CN_CONFIG']).read_text()); out=Path(os.environ['CN_OUTPUT']); out.mkdir(exist_ok=True,parents=True)
    h=None
    try:
        h=Harness(dut,config,out); await h.run(); h.close('PASS')
    except BaseException as exc:
        if h is not None: h.close('FAIL',str(exc))
        raise
