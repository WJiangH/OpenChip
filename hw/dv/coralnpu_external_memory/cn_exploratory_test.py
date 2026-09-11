"""Exploratory CNEM-21/23--27 scenarios; no positive acceptance is replaced."""
import json,os
from pathlib import Path
import cocotb
from checker import Checker,require
from cn_extmem_test import Harness
from exploratory_checker import TrapChecker
from exploratory_responder import FaultResponder,AbortResponder,abort_epoch

class ExploratoryHarness(Harness):
    def __init__(self,dut,config,out,mode):
        super().__init__(dut,config,out);self.mode=mode
        image=bytes(self.resp.memory)
        if mode=='error':self.check=TrapChecker(image,config);self.resp=FaultResponder(image,config)
        if mode=='abort':self.resp=AbortResponder(image,config)
        (out/'initial-image.bin').write_bytes(image)
        self.first_terminal_memory=None
    async def boot(self):
        await self.clocks(10);self.boot_check.reset_transition(self.cycle,'falling');self.d.io_aresetn.value=1
        await self.clocks(10)
        require(await self.csr(0x200000)==3,'CNEM-10 RESET_CONTROL readback')
        require(await self.csr(0x200004)==self.config['entry'],'CNEM-10 boot capture')
        await self.csr(0x200004,self.config['entry'])
        require(await self.csr(0x200004)==self.config['entry'],'CNEM-10 PC readback')
        self.resp.locked=True;self.image_info['locked_cycle']=self.cycle
        await self.csr(0x200000,1);await self.clocks(10)
        await self.csr(0x200000,0);self.check.release=self.cycle
        require(self.boot_check.release==self.check.release,'CNEM-10 release observer equality')
    async def tick(self):
        old_halt=self.check.halt;result=await super().tick()
        if self.mode=='error':self.check.observe_responder(self.cycle,self.resp.memory,len(self.resp.write_commits))
        if old_halt is None and self.check.halt is not None:
            require(self.resp.memory==self.check.mem,'Independent memory equality at terminal edge')
            self.first_terminal_memory=bytes(self.resp.memory)
            (self.out/'terminal-memory.bin').write_bytes(self.first_terminal_memory)
        return result
    async def negative(self):
        await self.boot()
        while self.check.halt is None:await self.tick()
        self.boot_check.finish()
        await self.clocks(32)
        self.check.finish()
    async def reach_abort(self):
        await self.boot()
        while True:
            if self.config['reset_kind']=='ar':
                q=self.check.reads.get(1)
                ready=q is not None and q['addr']==(self.config['entry']&~15)
            else:ready=self.check.aw is not None and self.check.aw['addr']==self.config['ret'] and self.check.w is None
            if ready:break
            await self.tick()
        # One additional edge explicitly witnesses the selected withheld response
        # or W half. Both deadlines remain unexpired, then reset cancels this epoch.
        await self.tick()
        witness=abort_epoch(self.check,self.resp,self.config['reset_kind'],self.config['entry'],self.config['ret'])
        self.d.io_aresetn.value=0
        for ch in ('r','b'):self.set('master',ch,'valid',0)
        for ch in ('ar','aw','w'):self.set('slave',ch,'valid',0)
        witness.update(assertion_cycle=self.cycle,assertion_phase='falling',run_id=self.config['run_id'],salt=self.config['salt'])
        return witness
    def close(self,verdict,error=None):
        self.trace.close();(self.out/'final-memory.bin').write_bytes(self.resp.memory)
        result={'verdict':verdict,'error':error,'mode':self.mode,'config':self.config,'image':self.image_info,
            'bindings':self.bindings,'host_transactions':self.host,'scoreboard':self.check.summary(),
            'schedule_counts':dict(self.resp.counts),'executed_cycles':self.cycle,
            'checked_scope':'v0.4 CNEM-21/23/24/25/31 negative terminal, 32-edge observation and protocol' if self.mode=='error' else 'CNEM-26/27 aborted epoch; no aborted terminal acceptance',
            'injection_events':getattr(self.resp,'injected',[]),
            'open_contract_question':None}
        (self.out/'verdict.json').write_text(json.dumps(result,indent=2)+'\n')

@cocotb.test()
async def external_memory_exploratory(dut):
    config=json.loads(Path(os.environ['CN_CONFIG']).read_text());out=Path(os.environ['CN_OUTPUT']);out.mkdir(parents=True,exist_ok=True)
    active=None
    try:
        if config['kind']=='error':
            active=ExploratoryHarness(dut,config,out,'error');await active.negative()
            active.close('PASS');active=None
        else:
            first={**config,'salt':0,'run_id':config['abort_run_id'],'epoch':0,'global_cycle_offset':0}
            aborted=out/'epoch-0-aborted';aborted.mkdir()
            active=ExploratoryHarness(dut,first,aborted,'abort');witness=await active.reach_abort()
            active.close('COORDINATED_ABORT_AS_SELECTED');active=None
            (out/'abort-witness.json').write_text(json.dumps(witness,indent=2)+'\n')
            recovery={**config,'salt':17,'run_id':config['run_id'],'epoch':1,'global_cycle_offset':witness['assertion_cycle']}
            recovered=out/'epoch-1-recovery';recovered.mkdir()
            # Fresh host/response/checker objects; no old queue or memory capability
            # is supplied. Constructor fully reloads ELF/BSS/formula inputs/record.
            active=Harness(dut,recovery,recovered);await active.run();active.close('PASS');active=None
            summary={'verdict':'PASS','kind':'reset','config':config,'abort_witness':witness,
                     'recovery_verdict':json.loads((recovered/'verdict.json').read_text()),
                     'checked_scope':'Selected abort witness, purge, cold reload, full salt17 positive recovery'}
            (out/'verdict.json').write_text(json.dumps(summary,indent=2)+'\n')
    except BaseException as exc:
        if active is not None:active.close('FAIL',str(exc))
        failure={'verdict':'FAIL','error':str(exc),'config':config}
        (out/'exploratory-failure.json').write_text(json.dumps(failure,indent=2)+'\n')
        if not (out/'verdict.json').exists():(out/'verdict.json').write_text(json.dumps(failure,indent=2)+'\n')
        raise
