"""Local conceptual architecture drawings; SVG and draw.io share one graph.

This is a diagram generator, not RTL, an executable SoC model, or IP-XACT.
"""
from pathlib import Path
import html
import json
import xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent
COLORS = {
    'control': ('#edf3fb', '#3468a0'),
    'data': ('#eaf5ef', '#28734e'),
    'security': ('#f4effa', '#785297'),
    'platform': ('#fff4e5', '#a76a22'),
    'neutral': ('#f3f5f7', '#52606d'),
}


class Drawing:
    def __init__(self, name, title, subtitle, width=1800, height=1140):
        self.name, self.title, self.subtitle = name, title, subtitle
        self.width, self.height = width, height
        self.nodes, self.edges, self.notes = [], [], []

    def node(self, key, x, y, w, h, lines, kind='neutral', group=False):
        self.nodes.append(dict(id=key, x=x, y=y, w=w, h=h,
                               lines=lines, kind=kind, group=group))

    def edge(self, source, target, points, label='', kind='data', dashed=False,
             both=False, label_at=None):
        self.edges.append(dict(id=f'e{len(self.edges)}', source=source,
                               target=target, points=points, label=label,
                               kind=kind, dashed=dashed, both=both,
                               label_at=label_at))

    def note(self, x, y, value, size=19):
        self.notes.append(dict(x=x, y=y, text=value, size=size))


soc = Drawing('01-soc', 'OpenChip NPU SoC | Top-level block diagram',
              'Architecture candidate v0.1 | logical connectivity, not floorplan | LOCAL DRAFT')
soc.node('chip', 30, 120, 1500, 955, ['SoC boundary'], group=True)
soc.node('cpu', 85, 180, 280, 130,
         ['RISC-V control CPU', 'RV32 core candidate', 'Firmware / dispatch / exceptions'], 'control')
soc.node('security', 445, 170, 430, 145,
         ['Security & boot domain', 'Caliptra subsystem candidate', 'RoT + management MCU + protected memory', 'Lifecycle / OTP / entropy integration'], 'security')
soc.node('crm', 1120, 255, 335, 90,
         ['Clock / reset / boot control', 'Boot: view 03 | clocks: view 04'], 'platform')
soc.node('fabric', 85, 410, 1370, 75,
         ['AXI4 system interconnect + access control', 'Request identity, region permissions, arbitration, error response'], 'data')
soc.node('rom', 85, 555, 245, 115,
         ['ROM / QSPI controller', 'Firmware image source', 'AXI target'], 'control')
soc.node('sram', 365, 555, 270, 115,
         ['Banked system SRAM', 'Code / queues / shared tensors', 'AXI target; capacity TBD'], 'data')
soc.node('memory', 735, 555, 290, 115,
         ['External-memory controller', 'DDR controller + PHY candidate', 'FPGA / ASIC platform adapter'], 'platform')
soc.node('apb', 1120, 555, 335, 95,
         ['AXI-to-APB bridge', 'Peripheral register access'], 'control')
soc.node('periph', 1120, 715, 335, 90,
         ['UART / GPIO / timer / watchdog', 'Low-bandwidth peripherals'], 'control')
soc.node('irq', 1120, 875, 335, 80,
         ['Interrupt aggregation', 'CPU interrupt delivery'], 'control')
soc.node('npu', 85, 765, 900, 230, ['NPU subsystem | project-owned compute'], 'data', group=True)
soc.node('npu_csr', 115, 825, 205, 100,
         ['Command / CSR', 'AXI4-Lite target', 'Validated descriptors'], 'control')
soc.node('npu_dma', 405, 825, 200, 100,
         ['Tensor DMA', 'AXI4 initiator', 'Data + command reads'], 'data')
soc.node('npu_core', 690, 825, 255, 100,
         ['Local SRAM + compute', 'Matrix MAC / vector / SFU', 'Detail: view 02'], 'data')
soc.node('recovery', 1570, 165, 195, 115,
         ['Recovery host', 'I3C / streaming boot', 'External test model'], 'security')
soc.node('dram', 1570, 550, 195, 125,
         ['External DRAM', 'Weights / tensors / KV', 'Board-specific part'], 'platform')
soc.edge('cpu', 'fabric', [(225,310),(225,410)], 'AXI4-Lite + adapter', 'control', both=True, label_at=(325,365))
soc.edge('security', 'fabric', [(655,315),(655,410)], 'AXI4 + trusted USER', 'security', both=True, label_at=(820,365))
soc.edge('security', 'recovery', [(875,205),(1570,205)], 'I3C', 'security', both=True, label_at=(1220,191))
soc.edge('crm','fabric',[(1300,345),(1300,410)],'clk / rst', 'platform', True, label_at=(1370,380))
soc.edge('fabric','rom',[(205,485),(205,555)],'AXI', 'control', both=True, label_at=(240,529))
soc.edge('fabric','sram',[(505,485),(505,555)],'AXI4',both=True,label_at=(553,529))
soc.edge('fabric','memory',[(880,485),(880,555)],'AXI4',both=True,label_at=(932,529))
soc.edge('memory','dram',[(1025,610),(1065,610),(1065,690),(1550,690),(1550,610),(1570,610)],
         'Physical memory interface', 'platform', both=True, label_at=(1300,685))
soc.edge('fabric','apb',[(1300,485),(1300,555)],'AXI4', 'control',both=True,label_at=(1350,529))
soc.edge('apb','periph',[(1300,650),(1300,715)],'APB','control',both=True,label_at=(1340,704))
soc.edge('fabric','npu_csr',[(105,485),(60,485),(60,875),(115,875)],
         'AXI4 to Lite', 'control',both=True,label_at=(165,719))
soc.edge('npu_dma','fabric',[(505,825),(505,725),(680,725),(680,485)],
         'AXI4 bursts',both=True,label_at=(602,713))
soc.edge('npu_csr','npu_dma',[(320,875),(405,875)],'dispatch','control',True,label_at=(364,854))
soc.edge('npu_dma','npu_core',[(605,875),(690,875)],'local data',both=True,label_at=(647,854))
soc.edge('npu','irq',[(985,915),(1120,915)],'done / fault','control',True,label_at=(1052,899))
soc.edge('periph','irq',[(1360,805),(1360,875)],'IRQ','control',True,label_at=(1410,846))
soc.edge('irq','cpu',[(1200,955),(1200,1030),(45,1030),(45,245),(85,245)],
         'CPU IRQ', 'control',True,label_at=(1030,1022))
soc.note(85,1056,'Security authorization / debug / reset sidebands are expanded in view 03, not implicit in AXI.')
soc.note(50,1115,'Solid arrows: interface traffic (double = bidirectional). Dashed: control / IRQ. Crossings without dots are not junctions.')

npu = Drawing('02-npu', 'OpenChip NPU | Compute and data movement',
              'Functional organization | candidate INT8 MAC + INT32 accumulation | precision / sizing not frozen', 1800, 1100)
npu.node('host',60,145,245,110,['CPU runtime', 'Addresses / descriptors', 'Doorbell / completion'], 'control')
npu.node('queue',395,145,340,110,['CSR + command processor', 'Descriptor validation / dependencies', 'Tile scheduling / completion'], 'control')
npu.node('ctl',865,145,360,110,['Compute control / scoreboards', 'DMA overlap + buffer ownership', 'Fault and cancellation handling'], 'control')
npu.node('axi',60,420,245,115,['System AXI4 fabric', 'SRAM / external DRAM', 'Data + descriptor traffic'], 'data')
npu.node('dma',395,420,340,115,['Tensor DMA / layout engine', 'Burst reads and writes', 'Packing / strides / alignment'], 'data')
npu.node('local',865,385,790,150,['Banked local tensor SRAM', 'Weight banks | activation banks | intermediate buffers', 'Double buffering candidate; bank ports and capacity from DSE'], 'data')
npu.node('matrix',865,625,335,130,['Matrix MAC engine', 'Tiled GEMM / GEMV mapping', 'INT8 operands; array shape TBD'], 'data')
npu.node('vector',1320,625,335,130,['Vector / reduction / SFU', 'Add / requant / activation', 'Norm / softmax: precision TBD'], 'data')
npu.node('acc',865,860,335,110,['Accumulator storage', 'INT32 candidate', 'Overflow contract required'], 'data')
npu.node('out',395,860,340,110,['Output / writeback', 'Format conversion / packing', 'Results and status'], 'data')
npu.node('irq',60,860,245,110,['Completion / fault IRQ', 'Host observes actual results', 'No internal state injection'], 'control')
npu.edge('host','queue',[(305,200),(395,200)],'AXI4-Lite','control',both=True,label_at=(348,180))
npu.edge('queue','ctl',[(735,200),(865,200)],'commands','control',True,label_at=(800,180))
npu.edge('queue','dma',[(550,255),(550,420)],'DMA descriptors','control',True,label_at=(655,345))
npu.edge('ctl','local',[(1000,255),(1000,385)],'ownership','control',True,label_at=(1080,328))
npu.edge('ctl','matrix',[(865,215),(785,215),(785,575),(980,575),(980,625)],'issue / done','control',True,both=True,label_at=(835,300))
npu.edge('ctl','vector',[(1225,200),(1710,200),(1710,685),(1655,685)],'issue / done','control',True,both=True,label_at=(1460,180))
npu.edge('axi','dma',[(305,478),(395,478)],'AXI4',both=True,label_at=(350,458))
npu.edge('dma','local',[(735,478),(865,478)],'local fabric',both=True,label_at=(800,458))
npu.edge('local','matrix',[(1030,535),(1030,625)],'W + X',both=True,label_at=(1080,583))
npu.edge('local','vector',[(1480,535),(1480,625)],'vectors',both=True,label_at=(1530,583))
npu.edge('matrix','acc',[(1030,755),(1030,860)],'partial sums',both=True,label_at=(1110,815))
npu.edge('acc','vector',[(1200,915),(1480,915),(1480,755)],'postprocess',both=True,label_at=(1360,904))
npu.edge('acc','out',[(865,915),(735,915)],'results',label_at=(800,897))
npu.edge('local','out',[(910,535),(810,535),(810,800),(620,800),(620,860)],'vector results',label_at=(714,790))
npu.edge('out','dma',[(450,860),(450,535)],'writeback stream',label_at=(550,695))
npu.edge('out','irq',[(395,915),(305,915)],'status','control',True,label_at=(350,895))
npu.note(60,1040,'Local data paths are SRAM/native or explicitly adapted streams; ready/valid alone does not claim AXI4-Stream compliance.')
npu.note(60,1070,'GEMV utilization and non-MAC operators need separate measurement; theoretical MAC count is not application throughput.')

boot = Drawing('03-boot', 'OpenChip | Reset, secure boot and execution authorization',
               'Proposed security-enabled system flow | generic roles, not a Caliptra signal-level specification',1800,1040)
boot.node('por',75,160,285,115,['Power / clock / reset', 'POR / clock stability', 'Board / process adaptation'], 'platform')
boot.node('seq',485,160,345,115,['SoC reset / boot sequencer', 'Start immutable management ROM', 'Keep application CPU held'], 'platform')
boot.node('rot',985,160,350,115,['Caliptra security domain', 'Initialize RoT / authenticate own FW', 'OTP / entropy / lifecycle inputs'], 'security')
boot.node('source',75,430,285,125,['Firmware image source', 'QSPI flash / recovery host', 'Untrusted image bytes'], 'neutral')
boot.node('stage',485,430,345,125,['Protected staging memory', 'Load application image / manifest', 'Prevent unauthorized mutation'], 'security')
boot.node('verify',985,430,350,125,['Authorize application firmware', 'Signature / policy / version checks', 'Management ROM uses RoT services'], 'security')
boot.node('permit',985,715,350,135,['Execution authorization', 'Lock verified executable bytes', 'Set bus / debug / DMA permissions'], 'security')
boot.node('run',485,715,345,135,['Release application CPU', 'Run NPU firmware / application', 'DMA restricted to assigned buffers'], 'control')
boot.node('fail',1435,430,300,125,['Reject / report / recover', 'Application remains held', 'No silent fallback to unsigned FW'], 'security')
boot.node('fault',1435,715,300,135,['Runtime fault / watchdog', 'Quiesce transactions before reset', 'Escalation policy TBD'], 'platform')
boot.edge('por','seq',[(360,218),(485,218)],'stable / reset','platform',True,label_at=(422,199))
boot.edge('seq','rot',[(830,218),(985,218)],'ordered bring-up','platform',True,label_at=(905,197))
boot.edge('source','stage',[(360,493),(485,493)],'image data','data',label_at=(423,473))
boot.edge('seq','stage',[(660,275),(660,430)],'ROM load control','control',True,label_at=(762,367))
boot.edge('rot','verify',[(1160,275),(1160,430)],'security services','security',True,label_at=(1270,367))
boot.edge('stage','verify',[(830,493),(985,493)],'image / manifest','data',label_at=(908,473))
boot.edge('verify','permit',[(1160,555),(1160,715)],'authorized','security',True,label_at=(1235,637))
boot.edge('verify','fail',[(1335,493),(1435,493)],'rejected','security',True,label_at=(1385,473))
boot.edge('permit','run',[(985,783),(830,783)],'release','security',True,label_at=(908,763))
boot.edge('run','fault',[(660,850),(660,915),(1590,915),(1590,850)],'fault / watchdog','platform',True,label_at=(1130,902))
boot.edge('fault','fail',[(1590,715),(1590,555)],'contain / recover','platform',True,label_at=(1648,640))
boot.note(75,968,'Clock/reset implementation view: control, NPU and security are logical domains; independent clocks / power islands are not yet selected.')
boot.note(75,1003,'Functional bring-up is a separate non-security acceptance stage. FPGA OTP/entropy models do not prove production silicon security.')

domains = Drawing('04-domains', 'OpenChip | Clock and reset connectivity',
                  'v0 candidate: one functional SoC clock; external-memory PHY is platform-dependent',1800,1040)
domains.node('ref',70,170,290,110,['Reference clock / reset pads', 'FPGA clock source or ASIC pads', 'Input conditioning'], 'platform')
domains.node('clk',495,170,355,110,['Clock platform adapter', 'Generate / select soc_clk', 'PLL choice and frequency TBD'], 'platform')
domains.node('rst',495,500,355,130,['Reset / boot sequencer', 'Condition external reset', 'Coordinate warm / cold resets'], 'platform')
domains.node('sec',1050,120,480,120,['Security subsystem', 'soc_clk + ordered reset / pwrgood', 'Upstream Caliptra release-specific rules'], 'security')
domains.node('cpu',1050,355,480,115,['Application CPU', 'soc_clk + cpu_rst', 'Release only after boot authorization'], 'control')
domains.node('npu',1050,590,480,115,['NPU / DMA / AXI / SRAM / APB', 'soc_clk + coordinated resets', 'Drain or explicitly abort transactions'], 'data')
domains.node('mem',1050,825,480,115,['Memory-controller / PHY adapter', 'soc_clk interface; mem_clk if required', 'CDC / reset crossings owned here'], 'platform')
domains.edge('ref','clk',[(360,225),(495,225)],'reference clock','platform',label_at=(425,205))
domains.edge('ref','rst',[(220,280),(220,565),(495,565)],'external reset','platform',True,label_at=(340,547))
domains.edge('clk','sec',[(850,190),(950,190),(950,155),(1050,155)],'soc_clk','platform',label_at=(992,143))
domains.edge('clk','cpu',[(850,190),(950,190),(950,395),(1050,395)],'soc_clk','platform',label_at=(992,383))
domains.edge('clk','npu',[(850,190),(950,190),(950,630),(1050,630)],'soc_clk','platform',label_at=(992,618))
domains.edge('clk','mem',[(850,190),(950,190),(950,855),(1050,855)],'soc_clk','platform',label_at=(992,843))
domains.edge('rst','sec',[(850,520),(880,520),(880,215),(1050,215)],'reset / pwrgood','control',True,label_at=(963,241))
domains.edge('rst','cpu',[(850,550),(900,550),(900,445),(1050,445)],'cpu_rst','control',True,label_at=(988,468))
domains.edge('rst','npu',[(850,580),(920,580),(920,680),(1050,680)],'system resets','control',True,label_at=(978,703))
domains.edge('rst','mem',[(850,610),(940,610),(940,915),(1050,915)],'memory reset','control',True,label_at=(978,938))
domains.edge('sec','rst',[(1530,180),(1630,180),(1630,750),(700,750),(700,630)],'boot authorization / escalation','security',True,label_at=(1330,772))
domains.note(70,960,'Clock lines share soc_clk; reset branches are separately controlled outputs. Physical clock-tree synthesis is not represented.')
domains.note(70,995,'No independent power islands selected in v0. Low-power states, isolation, retention and DFT controls require separate implementation views.')


def render_svg(d):
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{d.width}" height="{d.height}" viewBox="0 0 {d.width} {d.height}" role="img">',
         f'<title>{html.escape(d.title)}</title>',f'<desc>{html.escape(d.subtitle)}</desc>',
         '<rect width="100%" height="100%" fill="white"/>',
         '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#182b3a} .edgeLabel{paint-order:stroke;stroke:white;stroke-width:7;stroke-linejoin:round}</style>', '<defs>']
    for k,(_,stroke) in COLORS.items():
        out.append(f'<marker id="arrow-{k}" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto-start-reverse" markerUnits="userSpaceOnUse"><path d="M0,0 L10,5 L0,10 Z" fill="{stroke}"/></marker>')
    out.append('</defs>')
    out.append(f'<text x="50" y="52" font-size="31" font-weight="bold">{html.escape(d.title)}</text>')
    out.append(f'<text x="50" y="88" font-size="21">{html.escape(d.subtitle)}</text>')
    for n in d.nodes:
        fill,stroke=COLORS[n['kind']]
        if n['group']: fill='white'
        out.append(f'<rect x="{n["x"]}" y="{n["y"]}" width="{n["w"]}" height="{n["h"]}" rx="3" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        if n['group']:
            out.append(f'<text x="{n["x"]+15}" y="{n["y"]+30}" font-size="20" font-weight="bold">{html.escape(n["lines"][0])}</text>')
        else:
            y=n['y']+n['h']/2-(len(n['lines'])-1)*13+7
            for i,line in enumerate(n['lines']):
                out.append(f'<text x="{n["x"]+n["w"]/2}" y="{y+i*26}" text-anchor="middle" font-size="{21 if i==0 else 18}" font-weight="{"bold" if i==0 else "normal"}">{html.escape(line)}</text>')
    for e in d.edges:
        stroke=COLORS[e['kind']][1]
        pts=' '.join(f'{x},{y}' for x,y in e['points'])
        dash=' stroke-dasharray="8 5"' if e['dashed'] else ''
        start=f' marker-start="url(#arrow-{e["kind"]})"' if e['both'] else ''
        out.append(f'<polyline points="{pts}" fill="none" stroke="{stroke}" stroke-width="2.5"{dash}{start} marker-end="url(#arrow-{e["kind"]})"/>')
        if e['label']:
            x,y=e['label_at']
            out.append(f'<text x="{x}" y="{y}" text-anchor="middle" font-size="18" class="edgeLabel">{html.escape(e["label"])}</text>')
    for n in d.notes:
        out.append(f'<text x="{n["x"]}" y="{n["y"]}" font-size="{n["size"]}">{html.escape(n["text"])}</text>')
    out.append('</svg>')
    (OUT/f'{d.name}.svg').write_text('\n'.join(out))


def add_drawio_page(mxfile,d):
    diagram=ET.SubElement(mxfile,'diagram',id=d.name,name=d.name)
    model=ET.SubElement(diagram,'mxGraphModel',page='1',pageScale='1',pageWidth=str(d.width),pageHeight=str(d.height),grid='1',gridSize='10')
    root=ET.SubElement(model,'root')
    ET.SubElement(root,'mxCell',id='0');ET.SubElement(root,'mxCell',id='1',parent='0')
    nodes={n['id']:n for n in d.nodes}
    for n in d.nodes:
        fill,stroke=COLORS[n['kind']]
        style=f'rounded=0;whiteSpace=wrap;html=0;fontSize=20;fontColor=#182b3a;fillColor={fill};strokeColor={stroke};strokeWidth=2;'
        if n['group']: style+='fillColor=none;verticalAlign=top;align=left;spacing=14;'
        c=ET.SubElement(root,'mxCell',id=n['id'],value='\n'.join(n['lines']),style=style,vertex='1',parent='1')
        ET.SubElement(c,'mxGeometry',x=str(n['x']),y=str(n['y']),width=str(n['w']),height=str(n['h']),attrib={'as':'geometry'})
    for e in d.edges:
        src,tgt=nodes[e['source']],nodes[e['target']]
        x0,y0=e['points'][0];x1,y1=e['points'][-1]
        style=(f'edgeStyle=none;rounded=0;html=0;fontSize=18;strokeWidth=2.5;strokeColor={COLORS[e["kind"]][1]};'
               f'endArrow=block;startArrow={"block" if e["both"] else "none"};dashed={int(e["dashed"])};'
               f'exitX={(x0-src["x"])/src["w"]};exitY={(y0-src["y"])/src["h"]};exitPerimeter=0;'
               f'entryX={(x1-tgt["x"])/tgt["w"]};entryY={(y1-tgt["y"])/tgt["h"]};entryPerimeter=0;')
        c=ET.SubElement(root,'mxCell',id=e['id'],value='',style=style,edge='1',parent='1',source=e['source'],target=e['target'])
        g=ET.SubElement(c,'mxGeometry',relative='1',attrib={'as':'geometry'})
        arr=ET.SubElement(g,'Array',attrib={'as':'points'})
        for x,y in e['points'][1:-1]:ET.SubElement(arr,'mxPoint',x=str(x),y=str(y))
    notes=[dict(x=50,y=30,text=d.title,size=31),dict(x=50,y=69,text=d.subtitle,size=21),*d.notes]
    for e in d.edges:
        x,y=e['label_at'];w=max(40,len(e['label'])*9.5);notes.append(dict(x=x-w/2,y=y-18,text=e['label'],size=18,center=True,width=w))
    for i,n in enumerate(notes):
        style=f'text;html=0;align={"center" if n.get("center") else "left"};verticalAlign=top;fontSize={n["size"]};'
        if n.get('center'):style+='fillColor=#FFFFFF;'
        c=ET.SubElement(root,'mxCell',id=f'note{i}',value=n['text'],style=style,vertex='1',parent='1')
        ET.SubElement(c,'mxGeometry',x=str(n['x']),y=str(n['y']-15 if i>1 and not n.get('center') else n['y']),width=str(n['width'] if n.get('center') else d.width-n['x']-20),height='35',attrib={'as':'geometry'})


def main():
    drawings=[soc,npu,boot,domains]
    mx=ET.Element('mxfile',host='app.diagrams.net',type='device')
    for d in drawings:
        ids={n['id'] for n in d.nodes}
        assert len(ids)==len(d.nodes)
        for e in d.edges:
            assert e['source'] in ids and e['target'] in ids
        render_svg(d);add_drawio_page(mx,d)
    ET.indent(mx)
    ET.ElementTree(mx).write(OUT/'openchip-npu-v0.drawio',encoding='utf-8',xml_declaration=True)
    (OUT/'diagram-data.json').write_text(json.dumps([d.__dict__ for d in drawings],indent=2))
    print(f'Diagrams: PASS; {len(drawings)} views; {sum(len(d.edges) for d in drawings)} connections; SVG + editable draw.io generated.')


if __name__=='__main__':main()
