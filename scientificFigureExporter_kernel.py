# -*- coding: utf-8 -*-
"""Kernel-side Phase 1 exporter for Abaqus/CAE 2021.

The function name and keyword names are part of the AFXGuiCommand contract in
scientificFigureExporter_plugin.py.  Keep this module free of GUI imports so it
can be imported and smoke-tested in Abaqus noGUI mode.
"""

from __future__ import absolute_import

import os
import re
import time
import traceback

from abaqus import mdb, session
from abaqusConstants import OFF, ON, PNG
import abaqusConstants as abaqus_constants

from colorMaps import PALETTES
from scientificFigureExporter_state import restore, restore_session_state, snapshot


_STANDARD_VIEWS = (
    'Current', 'Iso', 'Front', 'Back', 'Left', 'Right', 'Top', 'Bottom',
)

_VIEW_COMPARE_PROPERTIES = (
    'nearPlane', 'farPlane', 'width', 'height', 'projection',
    'cameraPosition', 'cameraTarget', 'cameraUpVector',
    'viewOffsetX', 'viewOffsetY', 'fieldOfViewAngle', 'farPlaneMode',
)

_PHASE2A_VIEW_NAMES = (
    ('Current', 'viewCurrent'),
    ('Iso', 'viewIso'),
    ('Front', 'viewFront'),
    ('Back', 'viewBack'),
    ('Left', 'viewLeft'),
    ('Right', 'viewRight'),
    ('Top', 'viewTop'),
    ('Bottom', 'viewBottom'),
)

_ASPECT_RATIOS = {
    '16:9': 16.0 / 9.0,
    '3:2': 3.0 / 2.0,
    '4:3': 4.0 / 3.0,
    '1:1': 1.0,
}

_RENDER_STYLES = {
    'Shaded': 'SHADED',
    'Filled': 'FILLED',
    'Wireframe': 'WIREFRAME',
    'Hidden': 'HIDDEN',
}
_VISIBLE_EDGES = {
    'All': 'ALL',
    'Exterior': 'EXTERIOR',
    'Feature': 'FEATURE',
    'Free': 'FREE',
    'None': 'NONE',
}
_FORMAT_SPECS = {
    'PNG': ('PNG', 'pngOptions', '.png'),
    'JPG': ('PNG', 'pngOptions', '.jpg'),
    'TIFF': ('TIFF', 'tiffOptions', '.tif'),
    'SVG': ('SVG', 'svgOptions', '.svg'),
}
_HEX_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')

# A preview is intentionally process-local.  It is not written to an ODB or
# to the user's model.  Reset uses the same state.restore path as export.
_PREVIEW_STATES = {}
_PREVIEW_GLOBAL_STATE = None


def _text(value):
    if value is None:
        return ''
    try:
        return value.strip()
    except Exception:
        return str(value).strip()


def _positive_integer(value, label):
    try:
        number = int(value)
    except Exception:
        raise ValueError('%s must be an integer.' % label)
    if number <= 0:
        raise ValueError('%s must be greater than zero.' % label)
    return number


def _safe_base_name(value):
    value = _text(value)
    if not value:
        value = 'scientific_figure'
    value = os.path.basename(value)
    value = re.sub(r'[^A-Za-z0-9_.-]+', '_', value)
    value = value.strip(' .')
    if not value:
        value = 'scientific_figure'
    if value.lower().endswith('.png'):
        value = value[:-4]
    return value + '.png'


def _safe_stem(value):
    value = _text(value)
    if not value:
        value = 'scientific_figure'
    value = os.path.basename(value)
    value = re.sub(r'[^A-Za-z0-9_.-]+', '_', value)
    value = value.strip(' .')
    if not value:
        value = 'scientific_figure'
    for extension in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.svg',
                      '.eps'):
        if value.lower().endswith(extension):
            value = value[:-len(extension)]
            break
    return value.strip(' .') or 'scientific_figure'


def _current_viewport():
    name = session.currentViewportName
    if not name or name not in session.viewports.keys():
        raise ValueError('No current Abaqus viewport is available.')
    return session.viewports[name]


def _values_close(left, right):
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        scale = max(1.0, abs(left), abs(right))
        return abs(left - right) <= 1.0e-7 * scale
    if isinstance(left, (tuple, list)) and isinstance(right, (tuple, list)):
        if len(left) != len(right):
            return False
        return all(_values_close(a, b) for a, b in zip(left, right))
    return left == right


def _same_view(view, target):
    for name in _VIEW_COMPARE_PROPERTIES:
        try:
            if not _values_close(getattr(view, name), getattr(target, name)):
                return False
        except Exception:
            # If a version-specific property is unavailable, do not suppress
            # the requested standard-view operation.
            return False
    return True


def _set_view(viewport, view_name, state=None):
    view_name = _text(view_name) or 'Current'
    if view_name == 'Current':
        return False
    if view_name not in session.views.keys():
        raise ValueError('Abaqus standard view not found: %s' % view_name)
    target = session.views[view_name]
    if _same_view(viewport.view, target):
        return False
    # This positional form is used by the Abaqus replay examples and avoids
    # inventing a copy/serialization API for View objects.
    _mark_view_changed(state)
    viewport.view.setValues(target)
    return True


def _mark_view_changed(state):
    if state is None:
        return
    state['viewChanged'] = True
    try:
        state['viewHistorySteps'] = int(state.get('viewHistorySteps', 0)) + 1
    except Exception:
        state['viewHistorySteps'] = 1


def _view_values(view):
    values = {}
    for name in _VIEW_COMPARE_PROPERTIES:
        try:
            values[name] = getattr(view, name)
        except Exception:
            pass
    return values


def _view_values_equal(left, right):
    if not left or set(left.keys()) != set(right.keys()):
        return False
    return all(_values_close(value, right[name])
               for name, value in left.items())


def _fit_view(viewport, state=None):
    """Fit the displayable object and record a reversible view-history step."""
    before = _view_values(viewport.view)
    viewport.view.fitView()
    after = _view_values(viewport.view)
    changed = not _view_values_equal(before, after)
    if changed:
        _mark_view_changed(state)
    return changed


def _ensure_directory(path):
    path = _text(path)
    if not path:
        path = os.path.join(os.getcwd(), 'ScientificFigureExporter_output')
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        try:
            os.makedirs(path)
        except OSError:
            if not os.path.isdir(path):
                raise ValueError('Output directory does not exist and could not be created: %s' % path)
    if not os.access(path, os.W_OK):
        raise ValueError('Output directory is not writable: %s' % path)
    return path


def _error_message(error):
    text = _text(error)
    if text:
        return text
    return 'Scientific Figure Exporter failed.'


def _as_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(value)


def _selected_phase2a_views(viewCurrent, viewIso, viewFront, viewBack,
                            viewLeft, viewRight, viewTop, viewBottom):
    flags = {
        'viewCurrent': viewCurrent,
        'viewIso': viewIso,
        'viewFront': viewFront,
        'viewBack': viewBack,
        'viewLeft': viewLeft,
        'viewRight': viewRight,
        'viewTop': viewTop,
        'viewBottom': viewBottom,
    }
    selected = [name for name, key in _PHASE2A_VIEW_NAMES
                if _as_bool(flags[key])]
    if not selected:
        raise ValueError('Select at least one view.')
    return selected


def _viewport_names(viewportScope, viewportNames):
    current = _current_viewport()
    if int(viewportScope) == 0:
        return [session.currentViewportName]
    if int(viewportScope) != 1:
        raise ValueError('Unknown viewport scope: %s' % viewportScope)

    # ``viewportNames`` is a hidden GUI cache, not a user selection.  The
    # previous implementation trusted its stale value, so a dialog opened
    # while only Viewport: 1 existed continued exporting only Viewport: 1
    # after the user opened additional canvases.  Scope 1 explicitly means
    # all currently open viewports; query the live repository at export time.
    names = list(session.viewports.keys())
    if current in names:
        names.remove(current)
        names.insert(0, current)
    if not names:
        raise ValueError('No open Abaqus viewport is available.')
    return names


def _target_image_size(aspect, customAspect, lockRatio, resolutionMode,
                       width, height, physicalWidthMm, dpi):
    width = _positive_integer(width, 'Image width')
    height = _positive_integer(height, 'Image height')
    if int(resolutionMode) not in (0, 1):
        raise ValueError('Unknown resolution mode: %s' % resolutionMode)
    if int(resolutionMode) == 1:
        physical_width = float(physicalWidthMm)
        dpi_value = _positive_integer(dpi, 'DPI')
        if physical_width <= 0.0:
            raise ValueError('Publication width must be greater than zero.')
        width = int(round(physical_width / 25.4 * dpi_value))
        if width <= 0:
            raise ValueError('Calculated publication width is zero.')

    aspect = _text(aspect) or 'Current'
    if aspect == 'Current':
        ratio = float(width) / float(height)
    elif aspect in _ASPECT_RATIOS:
        ratio = _ASPECT_RATIOS[aspect]
    elif aspect == 'Custom':
        parts = _text(customAspect).split(':')
        if len(parts) != 2:
            raise ValueError('Custom aspect ratio must be W:H.')
        ratio = float(parts[0]) / float(parts[1])
        if ratio <= 0.0:
            raise ValueError('Custom aspect ratio must be positive.')
    else:
        raise ValueError('Unknown aspect ratio: %s' % aspect)

    if _as_bool(lockRatio) or int(resolutionMode) == 1:
        height = int(round(float(width) / ratio))
        if height <= 0:
            raise ValueError('Calculated image height is zero.')
    return width, height


def _rendered_file_path(output_dir, base_name, naming_template, viewport_name,
                        view_name, extension):
    stem = _safe_stem(base_name)
    template = _text(naming_template) or '{name}_{view}'
    values = {
        'name': stem,
        'view': _safe_stem(view_name),
        'viewport': _safe_stem(viewport_name),
    }
    try:
        rendered = template.format(**values)
    except Exception:
        # Keep the error boundary deterministic for Python 2.7 users: unknown
        # fields are treated as literal text rather than executing anything.
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace('{' + key + '}', value)
    rendered = os.path.basename(rendered)
    rendered = re.sub(r'[^A-Za-z0-9_.-]+', '_', rendered)
    rendered = rendered.strip(' .') or stem
    extension = extension.lower()
    if not rendered.lower().endswith(extension):
        rendered += extension
    return os.path.join(output_dir, rendered)


def _constant(name):
    value = getattr(abaqus_constants, name, None)
    if value is None:
        raise RuntimeError('Abaqus constant is unavailable in this release: %s' % name)
    return value


def _is_odb_viewport(viewport):
    try:
        displayed = viewport.displayedObject
        type_name = str(type(displayed)).lower()
        if 'odb' in type_name:
            return True
        return hasattr(displayed, 'steps') and hasattr(displayed,
                                                       'rootAssembly')
    except Exception:
        return False


def _is_contour_viewport(viewport):
    """Return whether an ODB viewport is currently plotting contours."""
    if not _is_odb_viewport(viewport):
        return False
    try:
        plot_state = viewport.odbDisplay.display.plotState
        contour_states = (
            _constant('CONTOURS_ON_DEF'), _constant('CONTOURS_ON_UNDEF'))
        return any(state in plot_state for state in contour_states)
    except Exception:
        # Keep this route conservative on releases with a different
        # plotState representation; contour options are not useful if the
        # viewport is not visibly in a contour plot.
        return False


def _normalize_hex_color(value, label):
    value = _text(value).upper()
    if not _HEX_COLOR.match(value):
        raise ValueError('%s must use #RRGGBB format.' % label)
    return value


def _format_spec(formatName):
    name = _text(formatName).upper()
    if name not in _FORMAT_SPECS:
        raise RuntimeError(
            'Format %s is not connected; choose PNG, JPG, TIFF, or SVG.' %
            name)
    if name == 'JPG':
        if os.name != 'nt':
            raise RuntimeError('JPG conversion is available on Windows only.')
        try:
            from scientificFigureExporter_jpeg import is_available
            if not is_available():
                raise RuntimeError('Windows GDI+ is unavailable.')
        except Exception as error:
            raise RuntimeError('JPG conversion is unavailable: %s' % error)
    constant_name, option_name, extension = _FORMAT_SPECS[name]
    constant = getattr(abaqus_constants, constant_name, None)
    option = getattr(session, option_name, None)
    if constant is None or option is None:
        raise RuntimeError('Abaqus %s output API is unavailable in this release.' % name)
    return name, constant, option, extension


def _apply_display_policy(viewport, renderStyle, visibleEdges,
                          translucencyEnabled, translucency):
    renderStyle = _text(renderStyle) or 'As Current'
    visibleEdges = _text(visibleEdges) or 'As Current'
    requested = (renderStyle != 'As Current' or
                 visibleEdges != 'As Current' or
                 _as_bool(translucencyEnabled))
    if not requested:
        return
    if not _is_odb_viewport(viewport):
        raise RuntimeError('Display style/edge/translucency routes are currently connected for ODB viewports only.')
    common = viewport.odbDisplay.commonOptions
    values = {}
    if renderStyle != 'As Current':
        if renderStyle not in _RENDER_STYLES:
            raise ValueError('Unknown render style: %s' % renderStyle)
        values['renderStyle'] = _constant(_RENDER_STYLES[renderStyle])
    if visibleEdges != 'As Current':
        if visibleEdges not in _VISIBLE_EDGES:
            raise ValueError('Unknown visible-edge mode: %s' % visibleEdges)
        values['visibleEdges'] = _constant(_VISIBLE_EDGES[visibleEdges])
    if _as_bool(translucencyEnabled):
        factor = float(translucency) / 100.0
        if factor < 0.0 or factor > 1.0:
            raise ValueError('Translucency must be between 0 and 100 percent.')
        values['translucency'] = ON
        values['translucencyFactor'] = factor
    if values:
        common.setValues(**values)


def _apply_annotation_policy(viewport, legend, compass, triad, titleBlock,
                             stateBlock, textArrows):
    annotation_options = viewport.viewportAnnotationOptions
    annotation_options.setValues(
        compass=ON if _as_bool(compass) else OFF)
    _apply_text_arrow_policy(viewport, textArrows)

    requested = (_as_bool(legend) or _as_bool(triad) or
                 _as_bool(titleBlock) or _as_bool(stateBlock))
    # Explicit OFF values are required for a second export/preview to be able
    # to turn a previously enabled annotation off.  A model viewport with no
    # requested annotation still remains a no-op because its ODB-only route is
    # not applicable.
    if not requested and not _is_odb_viewport(viewport):
        return
    if not _is_odb_viewport(viewport):
        raise RuntimeError('Annotation routes are currently connected for ODB viewports only.')
    values = {
        'legend': ON if _as_bool(legend) else OFF,
        'triad': ON if _as_bool(triad) else OFF,
        'title': ON if _as_bool(titleBlock) else OFF,
        'state': ON if _as_bool(stateBlock) else OFF,
    }
    annotation_options.setValues(**values)


def _is_text_or_arrow_annotation(annotation):
    try:
        type_name = str(type(annotation)).lower()
    except Exception:
        type_name = ''
    if not type_name:
        try:
            type_name = str(annotation.__class__.__name__).lower()
        except Exception:
            type_name = ''
    return 'text' in type_name or 'arrow' in type_name


def _text_arrow_objects(viewport):
    """Return visible and stored Text/Arrow objects for this display context."""
    sequence = getattr(viewport, 'annotationsToPlot', None)
    if sequence is None:
        return []
    try:
        objects = [annotation for annotation in sequence
                   if _is_text_or_arrow_annotation(annotation)]
    except Exception:
        objects = []

    repositories = []
    try:
        if _is_odb_viewport(viewport):
            repositories.append(
                viewport.displayedObject.userData.annotations)
    except Exception:
        pass
    try:
        repositories.append(mdb.annotations)
    except Exception:
        pass
    for repository in repositories:
        try:
            for name in repository.keys():
                annotation = repository[name]
                if (_is_text_or_arrow_annotation(annotation) and
                        annotation not in objects):
                    objects.append(annotation)
        except Exception:
            pass
    return objects


def _apply_text_arrow_policy(viewport, enabled):
    sequence = getattr(viewport, 'annotationsToPlot', None)
    if sequence is None:
        if _as_bool(enabled):
            raise RuntimeError(
                'This Abaqus viewport does not expose Text/Arrow annotations.')
        return
    if _as_bool(enabled):
        current = list(sequence)
        for annotation in _text_arrow_objects(viewport):
            if annotation not in current:
                viewport.plotAnnotation(annotation)
                current = list(sequence)
    else:
        for annotation in list(sequence):
            if _is_text_or_arrow_annotation(annotation):
                viewport.hideAnnotation(annotation)


def _ensure_spectrum(spectrumName, reverseSpectrum):
    name = _text(spectrumName) or 'Abaqus Default'
    if name == 'Abaqus Default':
        if _as_bool(reverseSpectrum):
            raise RuntimeError('Reverse spectrum requires one of the named Scientific Figure Exporter palettes.')
        return None, []
    if name not in PALETTES:
        raise ValueError('Unknown Scientific Figure Exporter palette: %s' % name)
    colors = tuple(PALETTES[name])
    suffix = '_reversed' if _as_bool(reverseSpectrum) else ''
    internal_name = '__ScientificFigureExporter_%s%s__' % (
        _safe_stem(name).replace('.', '_'), suffix)
    import visualization
    created = []
    if internal_name not in session.spectrums.keys():
        session.Spectrum(name=internal_name,
                         colors=tuple(reversed(colors)) if suffix else colors)
        created.append(internal_name)
    return internal_name, created


def _apply_contour_policy(viewport, spectrumName, reverseSpectrum,
                          intervals, contourRange, manualMin, manualMax):
    name = _text(spectrumName) or 'Abaqus Default'
    contourRange = _text(contourRange) or 'Current'
    intervals = int(intervals)
    if intervals < 5 or intervals > 24:
        raise ValueError('Contour intervals must be between 5 and 24.')
    if contourRange not in ('Current', 'Auto', 'Manual'):
        raise ValueError('Unknown contour range: %s' % contourRange)
    requested = (name != 'Abaqus Default' or _as_bool(reverseSpectrum) or
                 intervals != 12 or contourRange != 'Current')
    if not requested:
        return []
    if not _is_odb_viewport(viewport):
        raise RuntimeError('Contour routes are currently connected for ODB viewports only.')
    if not _is_contour_viewport(viewport):
        raise RuntimeError('Contour routes require an active ODB contour plot.')
    internal_name, created = _ensure_spectrum(name, reverseSpectrum)
    values = {'numIntervals': intervals}
    if internal_name is not None:
        values['spectrum'] = internal_name
    if contourRange == 'Auto':
        values['minAutoCompute'] = ON
        values['maxAutoCompute'] = ON
    elif contourRange == 'Manual':
        minimum = float(manualMin)
        maximum = float(manualMax)
        if minimum >= maximum:
            raise ValueError('Manual minimum must be less than maximum.')
        values['minAutoCompute'] = OFF
        values['maxAutoCompute'] = OFF
        values['minValue'] = minimum
        values['maxValue'] = maximum
    viewport.odbDisplay.contourOptions.setValues(**values)
    return created


def _validate_phase2a_controls(renderStyle, visibleEdges,
                               autoFit, translucencyEnabled, translucency,
                               legend, compass, triad, titleBlock,
                               stateBlock, textArrows, spectrumName,
                               reverseSpectrum, intervals, contourRange,
                               manualMin, manualMax, backgroundMode,
                               backgroundTop, backgroundBottom, exportMode,
                               formatName):
    if _text(renderStyle) not in tuple(['As Current'] + list(_RENDER_STYLES.keys())):
        raise ValueError('Unknown render style: %s' % renderStyle)
    if _text(visibleEdges) not in tuple(['As Current'] + list(_VISIBLE_EDGES.keys())):
        raise ValueError('Unknown visible-edge mode: %s' % visibleEdges)
    if (_text(renderStyle) == 'Wireframe' and
            _text(visibleEdges) == 'None'):
        raise ValueError('Wireframe cannot be combined with Visible edges = None.')
    if _as_bool(translucencyEnabled):
        factor = float(translucency)
        if factor < 0.0 or factor > 100.0:
            raise ValueError('Translucency must be between 0 and 100 percent.')
        if _text(renderStyle) == 'Wireframe':
            raise ValueError('Translucency is not available for Wireframe output.')
    if _text(spectrumName) not in tuple(['', 'Abaqus Default'] + list(PALETTES.keys())):
        raise ValueError('Unknown Scientific Figure Exporter palette: %s' % spectrumName)
    if int(intervals) < 5 or int(intervals) > 24:
        raise ValueError('Contour intervals must be between 5 and 24.')
    if _text(contourRange) not in ('', 'Current', 'Auto', 'Manual'):
        raise ValueError('Unknown contour range: %s' % contourRange)
    if _text(contourRange) == 'Manual' and float(manualMin) >= float(manualMax):
        raise ValueError('Manual minimum must be less than maximum.')
    if int(backgroundMode) not in (0, 1, 2, 3):
        raise ValueError('Unknown background mode: %s' % backgroundMode)
    if int(backgroundMode) in (1, 2):
        _normalize_hex_color(backgroundTop, 'Background top color')
    if int(backgroundMode) == 2:
        _normalize_hex_color(backgroundBottom, 'Background bottom color')
    if int(exportMode) not in (0, 1):
        raise ValueError('Unknown output layout: %s' % exportMode)
    _format_spec(formatName)


def _apply_phase2a_print_policy(backgroundMode, backgroundTop='#FFFFFF',
                                 backgroundBottom='#FFFFFF'):
    # These are the same native printOptions used by the verified Phase 1
    # route.  All mutations are restored by the caller.
    # Scientific output should not contain the native viewport border/title;
    # annotations are controlled independently through viewportAnnotationOptions.
    session.printOptions.setValues(vpDecorations=OFF, reduceColors=False)
    if int(backgroundMode) == 3:
        session.printOptions.setValues(vpBackground=OFF)
    elif int(backgroundMode) in (1, 2):
        top = _normalize_hex_color(backgroundTop, 'Background top color')
        style_name = 'SOLID' if int(backgroundMode) == 1 else 'GRADIENT'
        values = {
            'backgroundOverride': ON,
            'backgroundStyle': _constant(style_name),
            'backgroundColor': top,
        }
        if int(backgroundMode) == 2:
            values['backgroundBottomColor'] = _normalize_hex_color(
                backgroundBottom, 'Background bottom color')
        session.graphicsOptions.setValues(**values)
        session.printOptions.setValues(vpBackground=ON)
    elif int(backgroundMode) != 0:
        raise RuntimeError('Unsupported Phase 2A background mode: %s' % backgroundMode)


def _apply_phase2a_settings(viewport, renderStyle, visibleEdges,
                            translucencyEnabled, translucency, legend,
                            compass, triad, titleBlock, stateBlock,
                            textArrows, spectrumName, reverseSpectrum,
                            intervals, contourRange, manualMin, manualMax,
                            backgroundMode, backgroundTop, backgroundBottom):
    created = []
    try:
        created = _apply_contour_policy(
            viewport, spectrumName, reverseSpectrum, intervals, contourRange,
            manualMin, manualMax)
        _apply_display_policy(viewport, renderStyle, visibleEdges,
                              translucencyEnabled, translucency)
        _apply_annotation_policy(viewport, legend, compass, triad, titleBlock,
                                 stateBlock, textArrows)
        _apply_phase2a_print_policy(backgroundMode, backgroundTop,
                                    backgroundBottom)
        return created
    except Exception:
        _delete_created_spectrums(created)
        raise


def _apply_phase2a_settings_from_dict(viewport, settings):
    return _apply_phase2a_settings(
        viewport, settings['renderStyle'], settings['visibleEdges'],
        settings['translucencyEnabled'], settings['translucency'],
        settings['legend'], settings['compass'], settings['triad'],
        settings['titleBlock'], settings['stateBlock'], settings['textArrows'],
        settings['spectrumName'], settings['reverseSpectrum'],
        settings['intervals'], settings['contourRange'], settings['manualMin'],
        settings['manualMax'], settings['backgroundMode'],
        settings['backgroundTop'], settings['backgroundBottom'])


def _set_format_size(option, width, height):
    option.setValues(imageSize=(width, height))


def _unique_temporary_png_base(output_path):
    stamp = int(time.time() * 1000)
    for index in range(1000):
        candidate = '%s.__sfe_%d_%d_%d' % (
            output_path, os.getpid(), stamp, index)
        if (not os.path.exists(candidate) and
                not os.path.exists(candidate + '.png')):
            return candidate
    raise RuntimeError('Could not allocate a temporary PNG for JPG export.')


def _print_to_file(output_path, format_spec, canvas_viewports,
                   resolution_dpi=0):
    format_name, format_constant, unused_option, unused_extension = format_spec
    if format_name != 'JPG':
        session.printToFile(fileName=output_path, format=format_constant,
                            canvasObjects=tuple(canvas_viewports))
        return output_path

    from scientificFigureExporter_jpeg import png_to_jpeg
    temporary_base = _unique_temporary_png_base(output_path)
    temporary_candidates = (temporary_base + '.png', temporary_base)
    try:
        # Abaqus has no native JPEG print format. Render through its verified
        # PNG route, then use the Windows GDI+ JPEG encoder at quality 95.
        session.printToFile(fileName=temporary_base, format=PNG,
                            canvasObjects=tuple(canvas_viewports))
        temporary_png = None
        for candidate in temporary_candidates:
            if os.path.isfile(candidate):
                temporary_png = candidate
                break
        if temporary_png is None:
            raise RuntimeError(
                'Abaqus did not create the temporary PNG for JPG export.')
        png_to_jpeg(temporary_png, output_path, quality=95,
                    resolution=resolution_dpi)
        return output_path
    finally:
        for path in temporary_candidates:
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except Exception:
                pass


def _export_one_image(viewport, view_name, output_path, width, height,
                      format_spec, autoFit=False, resolutionDpi=0):
    format_name, format_constant, option, extension = format_spec
    view_state = {'viewChanged': False, 'viewHistorySteps': 0}
    try:
        _set_view(viewport, view_name, view_state)
        if _as_bool(autoFit):
            _fit_view(viewport, view_state)
        _set_format_size(option, width, height)
        _print_to_file(output_path, format_spec, (viewport,), resolutionDpi)
    finally:
        if view_state.get('viewChanged', False):
            restore(session, viewport, view_state,
                    restore_session_options=False, make_current=False)


def _viewport_dimension(viewport, name, fallback):
    try:
        value = float(getattr(viewport, name))
        if value > 0.0:
            return value
    except Exception:
        pass
    return float(fallback)


def _unique_temporary_viewport_name():
    index = 1
    while True:
        name = '__ScientificFigureExporter_canvas_%d__' % index
        if name not in session.viewports.keys():
            return name
        index += 1


def _create_combined_viewports(source_viewport, selected_views):
    """Create one native canvas viewport per requested standard view.

    This path is used when more than one standard view is selected but only a
    single current viewport can supply the displayed object.  Abaqus' native
    ``printToFile(canvasObjects=...)`` then treats these temporary viewports as
    real side-by-side canvas objects; they are removed in the caller's
    ``finally`` block.
    """
    created_names = []
    viewports = []
    panel_width = _viewport_dimension(source_viewport, 'width', 400.0)
    panel_height = _viewport_dimension(source_viewport, 'height', 300.0)
    displayed_object = source_viewport.displayedObject
    try:
        for index, view_name in enumerate(selected_views):
            name = _unique_temporary_viewport_name()
            viewport = session.Viewport(
                name=name, origin=(panel_width * index, 0.0),
                width=panel_width, height=panel_height)
            created_names.append(name)
            viewport.setValues(displayedObject=displayed_object)
            if view_name == 'Current':
                # View.setValues accepts another native View object.  This
                # copies the user's current camera into the temporary panel.
                viewport.view.setValues(source_viewport.view)
            else:
                if view_name not in session.views.keys():
                    raise ValueError('Abaqus standard view not found: %s' %
                                     view_name)
                viewport.view.setValues(session.views[view_name])
            viewports.append(viewport)
    except Exception:
        for name in created_names:
            try:
                del session.viewports[name]
            except Exception:
                pass
        raise
    return viewports, created_names


def _export_combined_canvas(source_viewports, selected_views, output_path,
                            width, height, format_spec, settings):
    """Export a single native canvas containing the requested panels.

    Semantics are deliberately explicit:

    * ``Current`` alone combines every live open viewport in scope, preserving
      the user's existing three-panel layout.
    * One selected standard view is applied to every viewport in scope.
    * Multiple selected views create one temporary panel per selected view,
      using the current viewport's displayed object.  This supports a single
      viewport plus Current/Iso/Front (or similar) selections.
    """
    format_name, format_constant, option, extension = format_spec
    source_states = []
    temporary_names = []
    created_spectrums = []
    canvas_viewports = []
    temporary_mode = len(selected_views) > 1
    if temporary_mode and len(source_viewports) > 1:
        raise ValueError(
            'Combined canvas with multiple selected views and All open '
            'viewports is not supported yet. Choose one view, or choose '
            'Current viewport for a multi-view canvas.')
    try:
        if temporary_mode:
            source = source_viewports[0]
            source_state = snapshot(session, source)
            source_states.append((source, source_state))
            canvas_viewports, temporary_names = _create_combined_viewports(
                source, selected_views)
            for viewport in canvas_viewports:
                viewport.makeCurrent()
                created_spectrums.extend(
                    _apply_phase2a_settings_from_dict(viewport, settings))
                if _as_bool(settings.get('autoFit', 0)):
                    _fit_view(viewport)
        else:
            view_name = selected_views[0]
            for viewport in source_viewports:
                state = snapshot(session, viewport)
                source_states.append((viewport, state))
                viewport.makeCurrent()
                _set_view(viewport, view_name, state)
                created_spectrums.extend(
                    _apply_phase2a_settings_from_dict(viewport, settings))
                if _as_bool(settings.get('autoFit', 0)):
                    _fit_view(viewport, state)
                canvas_viewports.append(viewport)

        _set_format_size(option, width, height)
        _print_to_file(output_path, format_spec, canvas_viewports,
                       settings.get('resolutionDpi', 0))
        return output_path
    finally:
        # Restore the session/viewport settings before deleting temporary
        # panels.  restore() also makes the saved original viewport current.
        for viewport, state in reversed(source_states):
            try:
                restore(session, viewport, state)
            except Exception:
                pass
        _delete_created_spectrums(created_spectrums)
        for name in temporary_names:
            try:
                del session.viewports[name]
            except Exception:
                pass


def _preview_view(selected_views):
    for name in selected_views:
        if name != 'Current':
            return name
    return 'Current'


def _preview_thumbnail_size(width, height):
    """Scale output dimensions into the fixed in-dialog preview area."""
    scale = min(1.0, 420.0 / float(width), 315.0 / float(height))
    return (max(1, int(round(float(width) * scale))),
            max(1, int(round(float(height) * scale))))


def _write_ui_preview(preview_path, viewport_names, selected_views,
                      export_mode, width, height, settings):
    """Render the first output or combined canvas as a temporary PNG."""
    preview_path = _text(preview_path)
    if not preview_path:
        return None
    preview_path = os.path.abspath(preview_path)
    if os.path.splitext(preview_path)[1].lower() != '.png':
        raise ValueError('The in-dialog preview path must end in .png.')
    if os.path.exists(preview_path):
        raise ValueError('Preview target already exists; request a new preview path.')
    output_dir = _ensure_directory(os.path.dirname(preview_path))
    preview_path = os.path.join(output_dir, os.path.basename(preview_path))
    preview_width, preview_height = _preview_thumbnail_size(width, height)
    format_spec = _format_spec('PNG')

    if int(export_mode) == 1:
        source_viewports = [session.viewports[name]
                            for name in viewport_names]
        return _export_combined_canvas(
            source_viewports, selected_views, preview_path, preview_width,
            preview_height, format_spec, settings)

    # Separate-file export can produce many files.  The UI shows the first
    # one (first live viewport, then first selected view) as a representative
    # thumbnail, while the actual Export action still writes every file.
    viewport_name = viewport_names[0]
    viewport = session.viewports[viewport_name]
    state = snapshot(session, viewport)
    created_spectrums = []
    try:
        viewport.makeCurrent()
        created_spectrums = _apply_phase2a_settings_from_dict(
            viewport, settings)
        _export_one_image(viewport, selected_views[0], preview_path,
                          preview_width, preview_height, format_spec,
                          autoFit=settings.get('autoFit', 0),
                          resolutionDpi=settings.get('resolutionDpi', 0))
    finally:
        restore(session, viewport, state)
        _delete_created_spectrums(created_spectrums)
    return preview_path


def _delete_created_spectrums(names):
    for spectrum_name in names:
        try:
            del session.spectrums[spectrum_name]
        except Exception:
            pass


def _reset_preview_states():
    global _PREVIEW_GLOBAL_STATE
    errors = []
    # Python 2 dictionaries do not provide a stable iteration order.  Restore
    # viewport-local state in a deterministic order and restore session-global
    # options exactly once after all viewports have been processed.
    names = list(_PREVIEW_STATES.keys())
    names.sort()
    for name in names:
        payload = _PREVIEW_STATES.get(name)
        state = payload.get('state', payload)
        try:
            viewport = session.viewports[name]
            restore(session, viewport, state, restore_session_options=False,
                    make_current=False)
        except Exception as error:
            errors.append('%s: %s' % (name, error))
        finally:
            _delete_created_spectrums(payload.get('createdSpectrums', []))
    global_state = _PREVIEW_GLOBAL_STATE
    if global_state is not None:
        try:
            restore_session_state(session, global_state)
            original_name = global_state.get('viewportName')
            if original_name and original_name in session.viewports.keys():
                session.viewports[original_name].makeCurrent()
        except Exception as error:
            errors.append('session options: %s' % error)
    _PREVIEW_STATES.clear()
    _PREVIEW_GLOBAL_STATE = None
    if errors:
        raise RuntimeError('Preview reset failed: %s' % '; '.join(errors))


def exportFigures(action='export',
                  viewCurrent=1, viewIso=0, viewFront=0, viewBack=0,
                  viewLeft=0, viewRight=0, viewTop=0, viewBottom=0,
                  autoFit=0, viewportScope=0, viewportNames='', exportMode=0,
                  renderStyle='As Current', visibleEdges='As Current',
                  translucencyEnabled=0, translucency=0, legend=0, compass=0,
                  triad=0, titleBlock=0, stateBlock=0, textArrows=0,
                  spectrumName='Abaqus Default', reverseSpectrum=0,
                  intervals=12, contourRange='Current', manualMin=0.0,
                  manualMax=1.0, backgroundMode=0, backgroundTop='#FFFFFF',
                  backgroundBottom='#FFFFFF', aspect='Current',
                  customAspect='4:3', lockRatio=0, resolutionMode=0,
                  width=1600, height=1200, physicalWidthMm=160.0, dpi=300,
                  formatName='PNG', outputDir='',
                  baseName='scientific_figure',
                  namingTemplate='{name}_{view}', previewPath=''):
    """Phase 2A multi-view raster/vector command on the existing plug-in.

    Connected in this revision: selected standard views, current/all open
    viewport routing, ODB display/contour/annotation controls, PNG/JPG/TIFF/SVG
    output, explicit pixel/publication sizing, aspect calculation,
    directory/template naming, in-dialog rendered preview/reset, and
    solid/gradient/no-viewport background policies, plus native combined-canvas
    export. JPG is rendered through Abaqus PNG and converted with Windows GDI+.
    """
    action = _text(action).lower() or 'export'
    if action == 'reset':
        _reset_preview_states()
        return 'Preview reset.'
    if action not in ('export', 'preview'):
        raise ValueError('Unknown exporter action: %s' % action)

    if action == 'export' and _PREVIEW_STATES:
        # Export is a fresh, reversible operation.  Clear the temporary
        # preview baseline first so the export's finally block restores the
        # user's original state rather than leaving the preview behind.
        _reset_preview_states()

    selected_views = _selected_phase2a_views(
        viewCurrent, viewIso, viewFront, viewBack, viewLeft, viewRight,
        viewTop, viewBottom)
    _validate_phase2a_controls(
        renderStyle, visibleEdges, autoFit, translucencyEnabled, translucency,
        legend, compass, triad, titleBlock, stateBlock, textArrows,
        spectrumName, reverseSpectrum, intervals, contourRange, manualMin,
        manualMax, backgroundMode, backgroundTop, backgroundBottom, exportMode,
        formatName)
    viewport_list = _viewport_names(viewportScope, viewportNames)
    format_spec = _format_spec(formatName)
    width, height = _target_image_size(
        aspect, customAspect, lockRatio, resolutionMode, width, height,
        physicalWidthMm, dpi)
    settings = {
        'autoFit': autoFit,
        'resolutionDpi': dpi if int(resolutionMode) == 1 else 0,
        'renderStyle': renderStyle,
        'visibleEdges': visibleEdges,
        'translucencyEnabled': translucencyEnabled,
        'translucency': translucency,
        'legend': legend,
        'compass': compass,
        'triad': triad,
        'titleBlock': titleBlock,
        'stateBlock': stateBlock,
        'textArrows': textArrows,
        'spectrumName': spectrumName,
        'reverseSpectrum': reverseSpectrum,
        'intervals': intervals,
        'contourRange': contourRange,
        'manualMin': manualMin,
        'manualMax': manualMax,
        'backgroundMode': backgroundMode,
        'backgroundTop': backgroundTop,
        'backgroundBottom': backgroundBottom,
    }

    if action == 'preview':
        global _PREVIEW_GLOBAL_STATE
        # One state per viewport allows Reset to restore every viewport touched
        # by an all-open-viewports preview.  Repeated Preview replaces the
        # previous preview after first restoring it.
        if _PREVIEW_STATES:
            _reset_preview_states()
        # Session print/PNG/graphics options are global in Abaqus.  Capture
        # them once before the first viewport is mutated; taking a full
        # snapshot for every viewport would overwrite this baseline after the
        # first mutation.
        _PREVIEW_GLOBAL_STATE = snapshot(session, _current_viewport())
        preview_view = _preview_view(selected_views)
        preview_output = None
        try:
            # Capture every target before applying anything.  Render the UI
            # thumbnail from these original cameras, then leave the live
            # viewports in the existing temporary-preview state.
            for viewport_name in viewport_list:
                state = snapshot(session, session.viewports[viewport_name])
                _PREVIEW_STATES[viewport_name] = {
                    'state': state, 'createdSpectrums': []}

            if _text(previewPath):
                preview_output = _write_ui_preview(
                    previewPath, viewport_list, selected_views, exportMode,
                    width, height, settings)

            for viewport_name in viewport_list:
                viewport = session.viewports[viewport_name]
                payload = _PREVIEW_STATES[viewport_name]
                viewport.makeCurrent()
                payload['createdSpectrums'] = _apply_phase2a_settings(
                    viewport, renderStyle, visibleEdges,
                    translucencyEnabled, translucency, legend, compass, triad,
                    titleBlock, stateBlock, textArrows, spectrumName,
                    reverseSpectrum, intervals, contourRange, manualMin,
                    manualMax, backgroundMode, backgroundTop, backgroundBottom)
                _set_view(viewport, preview_view, payload['state'])
                if _as_bool(autoFit):
                    _fit_view(viewport, payload['state'])
        except Exception:
            try:
                _reset_preview_states()
            except Exception:
                pass
            raise
        message = 'Preview applied for %s.' % preview_view
        if preview_output:
            message += ' UI thumbnail: %s' % preview_output
        return message

    output_dir = _ensure_directory(outputDir)
    outputs = []
    seen_paths = {}
    original_viewport_name = session.currentViewportName
    try:
        if int(exportMode) == 1:
            output_path = _rendered_file_path(
                output_dir, baseName, namingTemplate, 'Combined', 'Combined',
                format_spec[3])
            if output_path in seen_paths:
                raise ValueError('Naming template produced duplicate output: %s' %
                                 output_path)
            seen_paths[output_path] = True
            outputs.append(_export_combined_canvas(
                [session.viewports[name] for name in viewport_list],
                selected_views, output_path, width, height, format_spec,
                settings))
        else:
            for viewport_name in viewport_list:
                if viewport_name not in session.viewports.keys():
                    raise ValueError('Viewport not found: %s' % viewport_name)
                viewport = session.viewports[viewport_name]
                state = snapshot(session, viewport)
                created_spectrums = []
                try:
                    viewport.makeCurrent()
                    created_spectrums = _apply_phase2a_settings_from_dict(
                        viewport, settings)
                    for view_name in selected_views:
                        output_path = _rendered_file_path(
                            output_dir, baseName, namingTemplate, viewport_name,
                            view_name, format_spec[3])
                        if output_path in seen_paths:
                            raise ValueError('Naming template produced duplicate output: %s' %
                                             output_path)
                        seen_paths[output_path] = True
                        _export_one_image(viewport, view_name, output_path,
                                          width, height, format_spec,
                                          autoFit=autoFit,
                                          resolutionDpi=settings.get(
                                              'resolutionDpi', 0))
                        outputs.append(output_path)
                finally:
                    restore(session, viewport, state)
                    _delete_created_spectrums(created_spectrums)
    except Exception as error:
        traceback.print_exc()
        raise RuntimeError(_error_message(error))
    finally:
        if original_viewport_name:
            try:
                session.viewports[original_viewport_name].makeCurrent()
            except Exception:
                pass
    return '|'.join(outputs)


def exportFigure(viewName='Current', outputDir='', baseName='scientific_figure',
                 width=1600, height=1200):
    """Export the active viewport to one PNG and restore changed state.

    Phase 1 deliberately handles one active viewport and PNG only.  Advanced
    display controls are added only after their object-specific API paths have
    focused regression tests.
    """
    viewport = _current_viewport()
    width = _positive_integer(width, 'Image width')
    height = _positive_integer(height, 'Image height')
    output_dir = _ensure_directory(outputDir)
    file_name = _safe_base_name(baseName)
    output_path = os.path.join(output_dir, file_name)
    state = snapshot(session, viewport)

    try:
        # _set_view marks the state before the Abaqus call.  If a
        # version-specific setValues call fails after partial mutation, finally
        # still attempts the native previous-view restoration.
        view_name = _text(viewName) or 'Current'
        _set_view(viewport, view_name, state)
        session.printOptions.setValues(vpBackground=OFF, vpDecorations=ON,
                                       reduceColors=False)
        session.pngOptions.setValues(imageSize=(width, height))
        session.printToFile(fileName=output_path, format=PNG,
                            canvasObjects=(viewport,))
    except Exception as error:
        # Keep the traceback in the Abaqus message area/replay log while
        # exposing a concise error to the AFX callback/user.
        traceback.print_exc()
        raise RuntimeError(_error_message(error))
    finally:
        restore(session, viewport, state)

    # AFX does not need a return value, but returning the path is useful for
    # direct noGUI smoke tests.
    return output_path
