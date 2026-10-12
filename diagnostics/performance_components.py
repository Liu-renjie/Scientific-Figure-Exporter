# -*- coding: utf-8 -*-
"""Run with Abaqus/CAE 2021 noGUI; source ODB is opened read-only."""
from __future__ import print_function
import os
import sys
import time
import json
import cProfile
import pstats
from abaqus import session
from abaqusConstants import CONTOURS_ON_DEF
from visualization import openOdb

ROOT = os.path.abspath(os.getcwd())
sys.path.insert(0, ROOT)
for name in ('scientificFigureExporter_form.py',
             'scientificFigureExporter_kernel.py',
             'scientificFigureExporter_state.py',
             'scientificFigureExporter_plugin.py'):
    with open(os.path.join(ROOT, name),'rb') as stream:
        compile(stream.read(), name, 'exec')
import scientificFigureExporter_kernel as k
OUT = os.path.join(ROOT, 'diagnostics', 'performance_output')
if not os.path.isdir(OUT):
    os.makedirs(OUT)
ODB = os.environ['SFE_BENCHMARK_ODB']
vp = session.viewports[session.currentViewportName]
odb = openOdb(path=ODB, readOnly=True)
vp.setValues(displayedObject=odb)
vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
step = list(odb.steps.keys())[-1]
vp.odbDisplay.setFrame(step=len(odb.steps)-1, frame=len(odb.steps[step].frames)-1)
baseline = k.snapshot(session, vp)
timings = {}
timings['primaryVariable'] = [str(v) for v in vp.odbDisplay.primaryVariable]

def measure(name, fn):
    start = time.time()
    value = fn()
    timings[name] = round(time.time()-start, 4)
    print(name, timings[name])
    return value

prof = cProfile.Profile()
prof.enable()
try:
    measure('snapshot', lambda: k.snapshot(session, vp))
    frames = odb.steps[step].frames
    measure('get_frame', lambda: frames[-1])
    frame = frames[-1]
    measure('get_output', lambda: frame.fieldOutputs['S'])
    field = frame.fieldOutputs['S']
    measure('locations', lambda: field.locations[0].position)
    measure('set_same_frame', lambda: vp.odbDisplay.setFrame(step=len(odb.steps)-1, frame=len(frames)-1))
    measure('set_primary', lambda: vp.odbDisplay.setPrimaryVariable(variableLabel='S', outputPosition=field.locations[0].position, refinement=k._field_refinement(field)))
    k.restore(session, vp, baseline)
    measure('native_png', lambda: session.printToFile(fileName=os.path.join(OUT, 'native'), format=k.PNG, canvasObjects=(vp,)))
    measure('plan_current', lambda: k.buildExportPlan(fieldOutputs='S|U', outputDir=OUT))
    measure('plan_frames', lambda: k.buildExportPlan(fieldOutputs='S|U', frameSelection=3, everyN=10, outputDir=OUT))
    path = os.path.join(OUT, 'preview_%d.png' % int(time.time()*1000))
    measure('preview', lambda: k.exportFigures(action='preview', fieldOutputs='S|U', previewPath=path, width=320, height=240))
    measure('reset', lambda: k.exportFigures(action='reset'))
    warm_path = os.path.join(OUT, 'preview_warm_%d.png' % int(time.time()*1000))
    measure('preview_warm', lambda: k.exportFigures(action='preview', fieldOutputs='S|U', previewPath=warm_path, width=320, height=240))
    k.exportFigures(action='reset')
    measure('export', lambda: k.exportFigures(fieldOutputs='S|U', outputDir=OUT, baseName='batch', width=320, height=240))
    measure('restore', lambda: k.restore(session, vp, baseline))
    timings['refreshMethods'] = [n for n in ('disableRefresh','enableRefresh','disableColorCodeUpdates','enableColorCodeUpdates') if hasattr(vp, n)]
    timings['fields'] = {name: {'components': list(odb.steps[step].frames[-1].fieldOutputs[name].componentLabels), 'invariants': [str(v) for v in odb.steps[step].frames[-1].fieldOutputs[name].validInvariants]} for name in ('S','U')}
finally:
    prof.disable()
    with open(os.path.join(OUT, 'timings.json'), 'w') as f:
        json.dump(timings, f, indent=2)
    with open(os.path.join(OUT, 'profile.txt'), 'w') as f:
        pstats.Stats(prof, stream=f).sort_stats('cumulative').print_stats(45)
    odb.close()
