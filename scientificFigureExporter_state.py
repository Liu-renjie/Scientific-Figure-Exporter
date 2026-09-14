# -*- coding: utf-8 -*-
"""Small, explicit session/viewport state snapshot for the exporter.

The Phase 1 fields remain unchanged.  Phase 2 adds only the session/viewport
objects that its connected display and output routes mutate; this is not an
attempt to serialize a complete Abaqus session.
"""


_VIEW_PROPERTIES = (
    'nearPlane', 'farPlane', 'width', 'height', 'projection',
    'cameraPosition', 'cameraTarget', 'cameraUpVector',
    'viewOffsetX', 'viewOffsetY', 'fieldOfViewAngle', 'farPlaneMode',
)

_PRINT_PROPERTIES = ('vpBackground', 'vpDecorations', 'reduceColors')
_PNG_PROPERTIES = ('imageSize',)
_FORMAT_PROPERTIES = ('imageSize', 'resolution', 'imageFormat')
_ODB_COMMON_PROPERTIES = (
    'renderStyle', 'visibleEdges', 'translucency', 'translucencyFactor',
)
_ODB_CONTOUR_PROPERTIES = (
    'spectrum', 'numIntervals', 'minAutoCompute', 'maxAutoCompute',
    'minValue', 'maxValue', 'outsideLimitsMode',
)
_ANNOTATION_PROPERTIES = (
    'annotations', 'compass', 'triad', 'legend', 'title', 'state')
_GRAPHICS_PROPERTIES = (
    'backgroundOverride', 'backgroundStyle', 'backgroundColor',
    'backgroundBottomColor',
)


def _read_properties(obj, names):
    values = {}
    for name in names:
        try:
            values[name] = getattr(obj, name)
        except Exception:
            # Abaqus object properties vary with displayed object/module.
            # Missing properties are intentionally omitted from the snapshot.
            pass
    return values


def snapshot(session, viewport):
    """Return a best-effort snapshot of exporter-mutable settings."""
    state = {
        'viewportName': session.currentViewportName,
        'viewChanged': False,
        'viewHistorySteps': 0,
        'view': _read_properties(viewport.view, _VIEW_PROPERTIES),
        'printOptions': _read_properties(session.printOptions,
                                          _PRINT_PROPERTIES),
        'pngOptions': _read_properties(session.pngOptions, _PNG_PROPERTIES),
        'formatOptions': {},
        'displayOptions': {},
        'annotationOptions': _read_properties(
            getattr(viewport, 'viewportAnnotationOptions', None),
            _ANNOTATION_PROPERTIES),
        'graphicsOptions': _read_properties(
            getattr(session, 'graphicsOptions', None),
            _GRAPHICS_PROPERTIES),
        'plottedAnnotations': _read_plotted_annotations(viewport),
    }
    for name in ('tiffOptions', 'svgOptions'):
        try:
            state['formatOptions'][name] = _read_properties(
                getattr(session, name), _FORMAT_PROPERTIES)
        except Exception:
            pass

    # The connected Phase 2 display path is ODB-specific.  Capturing these
    # two repositories is harmless for a model viewport because missing
    # properties are omitted and restore remains best-effort.
    try:
        odb_display = getattr(viewport, 'odbDisplay')
        state['displayOptions']['odbCommonOptions'] = _read_properties(
            getattr(odb_display, 'commonOptions'), _ODB_COMMON_PROPERTIES)
        state['displayOptions']['odbContourOptions'] = _read_properties(
            getattr(odb_display, 'contourOptions'), _ODB_CONTOUR_PROPERTIES)
    except Exception:
        pass
    return state


def _restore_properties(obj, values):
    if not values:
        return
    try:
        obj.setValues(**values)
        return
    except Exception:
        # Restore properties one at a time so one version-specific property
        # cannot prevent the remaining known properties from being restored.
        for name, value in values.items():
            try:
                obj.setValues(**{name: value})
            except Exception:
                pass


def _read_plotted_annotations(viewport):
    try:
        return tuple(viewport.annotationsToPlot)
    except Exception:
        return None


def _restore_plotted_annotations(viewport, target):
    if target is None:
        return
    try:
        sequence = viewport.annotationsToPlot
        current = list(sequence)
    except Exception:
        return

    for annotation in current:
        if annotation not in target:
            try:
                viewport.hideAnnotation(annotation)
            except Exception:
                pass

    try:
        current = list(viewport.annotationsToPlot)
    except Exception:
        current = []
    for index, annotation in enumerate(target):
        if annotation not in current:
            try:
                viewport.plotAnnotation(annotation, index)
                current = list(viewport.annotationsToPlot)
            except Exception:
                pass

    # Hiding and re-plotting annotations can change their z-order. Restore the
    # captured sequence order using Abaqus' native sequence operation.
    for desired_index, annotation in enumerate(target):
        try:
            current = list(viewport.annotationsToPlot)
            current_index = current.index(annotation)
            if current_index != desired_index:
                viewport.annotationsToPlot.moveBefore(
                    current_index, desired_index)
        except Exception:
            pass


def _restore_session_state(session, state):
    # Abaqus 2021 recomputes perspective clipping dimensions against the
    # active print canvas.  Restore the canvas/options first; restoring View
    # while the export aspect ratio is still active leaves a scaled view.
    for name, values in state.get('formatOptions', {}).items():
        try:
            _restore_properties(getattr(session, name), values)
        except Exception:
            pass
    _restore_properties(session.pngOptions, state.get('pngOptions', {}))
    _restore_properties(session.printOptions, state.get('printOptions', {}))
    _restore_properties(session.graphicsOptions,
                        state.get('graphicsOptions', {}))


def restore_session_state(session, state):
    """Restore only options that are global to the Abaqus session."""
    _restore_session_state(session, state)


def restore(session, viewport, state, restore_session_options=True,
            make_current=True):
    """Restore the settings captured by :func:`snapshot`.

    Preview reset can restore viewport-local state without repeatedly
    overwriting global session options.  The default preserves the Phase 1
    and export behaviour.
    """
    if restore_session_options:
        _restore_session_state(session, state)
    display_state = state.get('displayOptions', {})
    try:
        _restore_properties(viewport.odbDisplay.commonOptions,
                            display_state.get('odbCommonOptions', {}))
        _restore_properties(viewport.odbDisplay.contourOptions,
                            display_state.get('odbContourOptions', {}))
    except Exception:
        pass
    _restore_properties(getattr(viewport, 'viewportAnnotationOptions', None),
                        state.get('annotationOptions', {}))
    _restore_plotted_annotations(
        viewport, state.get('plottedAnnotations'))
    steps = state.get('viewHistorySteps')
    if steps is None:
        steps = 1 if state.get('viewChanged', False) else 0
    try:
        steps = max(0, int(steps))
    except Exception:
        steps = 1 if state.get('viewChanged', False) else 0
    if steps:
        # Directly setting all View members is unsafe in Abaqus 2021: a
        # perspective View with AUTOCOMPUTE recalculates clipping dimensions.
        # The native view history preserves the exact pre-change View.
        for unused in range(steps):
            try:
                viewport.view.previous()
            except Exception:
                break

    original_name = state.get('viewportName')
    if make_current and original_name:
        try:
            session.viewports[original_name].makeCurrent()
        except Exception:
            # The original viewport may have been closed by the user while a
            # command was running; do not hide the original export exception.
            pass
