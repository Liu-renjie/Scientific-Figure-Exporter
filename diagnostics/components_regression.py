# -*- coding: utf-8 -*-
"""Actual Abaqus 2021 component/invariant, preview and restore regression."""
from __future__ import print_function
import os
import sys
import json
import time
from abaqus import session
from abaqusConstants import CONTOURS_ON_DEF, INVARIANT
from visualization import openOdb

ROOT = os.path.abspath(os.getcwd())
sys.path.insert(0, ROOT)
import scientificFigureExporter_kernel as k
OUT = os.path.join(ROOT, 'diagnostics', 'performance_output')
odb = openOdb(path=os.environ['SFE_BENCHMARK_ODB'], readOnly=True)
vp = session.viewports[session.currentViewportName]
vp.setValues(displayedObject=odb)
vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
names = list(odb.steps.keys())
frames = odb.steps[names[-1]].frames
vp.odbDisplay.setFrame(step=len(names)-1, frame=len(frames)-1)
baseline = k.snapshot(session, vp)
report = {}
try:
    start = time.time()
    catalog = k.buildFieldCatalog()
    report['catalogSeconds'] = round(time.time()-start,4)
    report['catalog'] = catalog
    assert len(k._field_output_tokens('S|S, Mises')) == 1
    catalog_path = os.path.join(OUT, 'catalog_command.json')
    k.exportFigures(action='fields', planPath=catalog_path)
    with open(catalog_path,'r') as stream:
        assert 'S, Mises' in json.load(stream)['fields']
    report['refinements'] = []
    for request in catalog['fields']:
        if ',' not in request or not request.startswith(('S,', 'U,')):
            continue
        plan = k._build_batch_plan(vp, request)
        k._apply_odb_batch_state(vp, plan[0])
        expected = plan[0]['_fieldSpec']['refinement'][1]
        assert vp.odbDisplay.primaryVariable[5] == expected, request
        report['refinements'].append(request)
    k.restore(session, vp, baseline)
    assert tuple(vp.odbDisplay.primaryVariable) == baseline['odbResultState']['primaryVariable']
    assert tuple(vp.odbDisplay.fieldFrame) == baseline['odbResultState']['fieldFrame']
    for baseline_request in ('U, U1', 'S, S22'):
        k._apply_odb_batch_state(vp, k._build_batch_plan(vp, baseline_request)[0])
        alternate = k.snapshot(session, vp)
        k._apply_odb_batch_state(vp, k._build_batch_plan(vp, 'S, S11')[0])
        k.restore(session, vp, alternate)
        assert tuple(vp.odbDisplay.primaryVariable) == alternate['odbResultState']['primaryVariable']
    k.restore(session, vp, baseline)
    # Verify native tensor Mises even when validInvariants omits it.
    field = frames[-1].fieldOutputs['S']
    vp.odbDisplay.setPrimaryVariable(variableLabel='S', outputPosition=field.locations[0].position, refinement=(INVARIANT, 'Mises'))
    report['nativeMisesAccepted'] = vp.odbDisplay.primaryVariable[5] == 'Mises'
    report['stressType'] = str(field.type)
    k.restore(session, vp, baseline)
    rows = k.buildExportPlan(fieldOutputs='S, S11|S, S22|U, U1|U, Magnitude', frameSelection=4, specifiedFrames='0|%d' % (len(frames)-1), outputDir=OUT)
    assert len(rows) == 8
    assert len(set(row['path'] for row in rows)) == 8
    report['planCount'] = len(rows)
    # Preview only the first combination even if another requested output is invalid.
    path = os.path.join(OUT, 'components_preview_%d.png' % int(time.time()*1000))
    k.exportFigures(action='preview', fieldOutputs='S, S11|MISSING_TEST_FIELD', previewPath=path, width=320, height=240)
    assert os.path.getsize(path) > 100
    k.exportFigures(action='reset')
    assert tuple(vp.odbDisplay.primaryVariable) == baseline['odbResultState']['primaryVariable']
    try:
        k.exportFigures(fieldOutputs='S, INVALID_COMPONENT', outputDir=OUT, baseName='must_not_exist')
        raise AssertionError('Invalid component was accepted')
    except ValueError:
        pass
    result = k.exportFigures(fieldOutputs='S, S11|S, S22|U, U1|U, Magnitude', frameSelection=4, specifiedFrames='0|%d' % (len(frames)-1), outputDir=OUT, baseName='components', width=320, height=240)
    report['exportResult'] = result
    assert len(result.split('|')) == 8
    assert all(os.path.getsize(path) > 100 for path in result.split('|'))
    assert tuple(vp.odbDisplay.primaryVariable) == baseline['odbResultState']['primaryVariable']
    assert tuple(vp.odbDisplay.fieldFrame) == baseline['odbResultState']['fieldFrame']
    # Multi-view temporary canvas still exports components and removes all panels.
    vp_names = list(session.viewports.keys())
    k.exportFigures(fieldOutputs='S, S11', viewIso=1, exportMode=1, outputDir=OUT, baseName='components_combined', width=640, height=240)
    assert list(session.viewports.keys()) == vp_names
    assert tuple(vp.odbDisplay.primaryVariable) == baseline['odbResultState']['primaryVariable']
    combined_rows = k.buildExportPlan(fieldOutputs='S, S11', viewIso=1, exportMode=1, outputDir=OUT, baseName='components_combined')
    assert os.path.isfile(combined_rows[0]['path'])
    assert len(k._FIELD_METADATA_CACHE) <= 8
    report['status'] = 'PASS'
finally:
    with open(os.path.join(OUT, 'components_regression.json'),'w') as f:
        json.dump(report,f,indent=2)
    odb.close()
