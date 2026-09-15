"""Render every custom window family under Xvfb; never connects to hardware."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.test_plotter_workflow import WorkflowGUITest
from PlotterUI import descendants,RoundedButton
from PIL import ImageGrab,Image,ImageDraw
from pathlib import Path
WorkflowGUITest.setUpClass(); a=WorkflowGUITest.app;case=WorkflowGUITest();case.setUp();w=a.workflow
out=ROOT/'docs/design/gui-review-fixed';out.mkdir(exist_ok=True)
issues=[];images=[]
from tkinter import ttk, font
from PlotterErrorDialog import show_modal_error
for size in ('320x600','390x844','1280x900'):
 a.geometry(size);a.update();w.select_all()
 actions=[(kind,lambda k=kind:w.design_dialog(k)) for kind in ['TextDialog','ShapeDialog','TraceDialog','ArrangeDialog','CombineDialog','OutlineDialog','LayoutDialog','ContourDialog','WeedDialog','LayersDialog','CutPreviewDialog','ProjectsDialog','FirstCutDialog']]
 actions += [('Settings',lambda:w.settings('Appearance')),('Library',w.open_library),('Machine',w.open_machine),('Connection',w.connection_settings),('More',w.open_menu),('Error',lambda:show_modal_error(w,a,'Import failed','Invalid SVG content')),('Alarm',lambda:show_modal_error(w,a,'Controller alarm','ALARM:1 Hard limit triggered'))]
 for name,action in actions:
  d=action();a.update()
  variants=list(d.categories) if name=='Settings' else [name]
  if name=='FirstCutDialog': variants=list(range(5))
  if name=='Library': variants=['Materials','Tools']
  if name in ('Error','Alarm'): variants=[name,name+' details']
  for variant in variants:
   if name=='Settings':d.category.set(variant);d.choose_category();a.update()
   if name=='FirstCutDialog': d.step=variant;d.show();variant='Guide '+str(variant+1);a.update()
   if name=='Library':
    next(c for c in descendants(d) if isinstance(c,ttk.Notebook)).select(0 if variant=='Materials' else 1);a.update()
   if name in ('Error','Alarm') and 'details' in variant:
    next(c for c in descendants(d) if isinstance(c,RoundedButton) and c.cget('text')=='Show details').invoke();a.update()
   file=out/(variant.replace('/','-')+'-'+size+'.png');ImageGrab.grab().crop((0,0,a.winfo_width(),a.winfo_height())).save(file);images.append(file)
   for c in descendants(d):
    if isinstance(c,RoundedButton) and c.winfo_ismapped():
     x=c.winfo_rootx()-a.winfo_rootx();right=x+c.winfo_width()
     if c.winfo_height()<44: issues.append((size,str(variant),c.cget('text'),'short control',c.winfo_height()))
     measure=font.Font(c,font=c.cget('font')).measure
     if not c._icon and max(map(measure,c.cget('text').split('\n'))) > c.winfo_width()-4:
      issues.append((size,str(variant),c.cget('text'),'text clipped',c.winfo_width()))
     if x<0 or right>a.winfo_width():issues.append((size,variant,c.cget('text'),x,right))
  d.destroy();a.update()
 for step in range(3):
  w.show_step(step);a.update();file=out/(f'workspace-{step}-'+size+'.png');ImageGrab.grab().crop((0,0,a.winfo_width(),a.winfo_height())).save(file);images.append(file)
 w.show_step(0)
# Freeze background polling before presentation-only machine fixtures.
from types import SimpleNamespace
from CNC import CNC
from PlotterSequence import ToolStage
from PlotterAppearance import save_appearance
for timer in a.tk.splitlist(a.tk.call('after','info')): a.after_cancel(timer)
def capture(name, size):
 a.update();file=out/(name+'-'+size+'.png')
 ImageGrab.grab().crop((0,0,a.winfo_width(),a.winfo_height())).save(file);images.append(file)
for size in ('320x600','390x844','1280x900'):
 a.sender.firmware=None
 a.geometry(size);a.update();w.show_step(0)
 save_appearance(a,'Dark','Comfortable');capture('Dark design',size)
 d=w.settings('Appearance');capture('Dark settings',size);d.destroy()
 save_appearance(a,'Light','Comfortable')
 a.sender.serial=object();a.sender.firmware=SimpleNamespace(board='GRBLFilmCut',label='FilmCut simulated',ready=True,jog=True,identified=True)
 CNC.vars['state']='Idle';CNC.vars['pins']='P';w.show_step(2)
 a.sender.running=True;a.sender._gcount=5;a.sender._runLines=100
 for state,name in [('Run','Running'),('Hold:0','Paused')]:
  CNC.vars['state']=state;a.sender._pause=state.startswith('Hold');w.update_state();capture(name,size)
 a.sender.running=False;a.sender._pause=False;CNC.vars['state']='Idle'
 a.tool_sequence.active=True;a.tool_sequence.phase='waiting';a.tool_sequence.index=1
 a.tool_sequence.stages=(ToolStage('Pen',()),ToolStage('Knife',()))
 a.tool_sequence.message='Fit Knife · pass 2 of 2. Keep the mat loaded. Confirm the tool is fitted and aligned.'
 w.update_state();capture('Tool change',size);a.tool_sequence.active=False;a.tool_sequence.phase='idle'
 w._cut_started=True
 for stopped,name in [(True,'Stopped'),(False,'Job ended')]:
  w._stopped=stopped;w.update_state();capture(name,size)
 a.sender.serial=None;CNC.vars['state']='Not connected';w.update_state();capture('Connection lost',size)
 w._cut_started=False;w.show_step(0)
a.sender.serial=None;a.sender.firmware=None
(out/'measurements.json').write_text(json.dumps({'horizontal_issues':issues,'captures':[p.name for p in images]},indent=2))
print(json.dumps(issues,indent=2),flush=True)
for start in range(0,len(images),12):
 sheet=Image.new('RGB',(1280,1000),'#d7dfe3');draw=ImageDraw.Draw(sheet)
 for i,file in enumerate(images[start:start+12]):
  x=i%4*320;y=i//4*333;im=Image.open(file);im.thumbnail((310,300));sheet.paste(im,(x,y+30));draw.text((x,y+5),file.stem,fill='black')
 sheet.save(out/f'contact-{start//12}.png')
WorkflowGUITest.tearDownClass()

html='<html><head><meta name="viewport" content="width=device-width"><title>Foil Studio GUI review</title></head><body style="font:16px sans-serif;background:#f3f5f6;color:#20313c"><h1>Revised application screens</h1><p>Real Tk renders using isolated test preferences. Machine disconnected.</p><div style="display:flex;flex-wrap:wrap;gap:24px">'
import html as escape
for path in images:
 html+=f'<figure style="margin:0;max-width:420px"><figcaption>{escape.escape(path.stem)}</figcaption><a href="{path.name}"><img style="max-width:100%;max-height:640px" src="{path.name}"></a></figure>'
(out/'index.html').write_text(html+'</div></body></html>')
if issues:
 raise SystemExit(f'Visual geometry review found {len(issues)} control issues; see measurements.json')
