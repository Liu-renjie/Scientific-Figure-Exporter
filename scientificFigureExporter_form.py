# -*- coding: utf-8 -*-
"""AFX GUI for the Scientific Figure Exporter.

Phase 1 remains available through ``exportFigure``. This dialog adds the
multi-view architecture on top of the same plug-in entry point and uses
Abaqus-native view, annotation, display, and export routes.
"""

from __future__ import absolute_import

import os
import json
import tempfile
import uuid

from abaqusGui import *
from abaqusConstants import CONTOURS_ON_DEF, CONTOURS_ON_UNDEF

try:
    from afxW_AFXSlider import AFXSlider
    from afxW_AFXSlider import AFXSLIDER_INSIDE_BAR, AFXSLIDER_SHOW_VALUE
except ImportError:
    # Abaqus releases expose the same widget through afxW in some installs.
    from afxW import AFXSlider
    from afxW import AFXSLIDER_INSIDE_BAR, AFXSLIDER_SHOW_VALUE

from colorMaps import PALETTE_NAMES, PALETTES


_VIEW_NAMES = ('Current', 'Iso', 'Front', 'Back', 'Left', 'Right',
               'Top', 'Bottom')
_VIEW_KEY_NAMES = {
    'Current': 'viewCurrentKw',
    'Iso': 'viewIsoKw',
    'Front': 'viewFrontKw',
    'Back': 'viewBackKw',
    'Left': 'viewLeftKw',
    'Right': 'viewRightKw',
    'Top': 'viewTopKw',
    'Bottom': 'viewBottomKw',
}


def _afx_string(value):
    """Encode widget text for the Windows Abaqus GUI process."""
    try:
        if isinstance(value, unicode):
            try:
                return value.encode('mbcs')
            except Exception:
                return value.encode('utf-8')
    except NameError:
        pass
    return value


def _format_ui_text(template, args):
    """Format display text while decoding Python 2 byte-string arguments."""
    if not args:
        return _afx_string(template)
    try:
        if isinstance(template, unicode):
            unicode_args = []
            for value in args:
                if isinstance(value, unicode):
                    unicode_args.append(value)
                elif isinstance(value, str):
                    try:
                        unicode_args.append(value.decode('mbcs'))
                    except Exception:
                        unicode_args.append(value.decode('utf-8', 'replace'))
                else:
                    unicode_args.append(unicode(value))
            return _afx_string(template % tuple(unicode_args))
    except NameError:
        pass
    return _afx_string(template % args)


def _palette_colors(name):
    if name == 'Abaqus Default':
        # The kernel intentionally leaves Abaqus' native spectrum unchanged.
        # Its actual colors are not introspected here, so do not invent stops.
        return ()
    if name in PALETTES:
        return PALETTES[name]
    return ('#000000', '#444444', '#888888', '#BBBBBB', '#FFFFFF')


def _hex_rgb(value):
    value = value.lstrip('#')
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except Exception:
        return 128, 128, 128


def _is_odb_display(displayed):
    """Return whether an Abaqus viewport is displaying an ODB object."""
    try:
        type_name = str(type(displayed)).lower()
    except Exception:
        type_name = ''
    if 'odb' in type_name:
        return True
    try:
        return hasattr(displayed, 'steps') and hasattr(displayed,
                                                       'rootAssembly')
    except Exception:
        return False


def _is_contour_viewport(viewport):
    """Return whether an ODB viewport is currently plotting contours."""
    if not _is_odb_display(getattr(viewport, 'displayedObject', None)):
        return False
    try:
        plot_state = viewport.odbDisplay.display.plotState
        contour_states = (CONTOURS_ON_DEF, CONTOURS_ON_UNDEF)
        return any(state in plot_state for state in contour_states)
    except Exception:
        # The GUI must stay conservative when a release exposes a different
        # plot-state representation: contour-only widgets remain disabled.
        return False


def _field_output_request_key(value):
    """Normalize a field label for matching saved GUI selections."""
    try:
        if isinstance(value, unicode):
            value = value.encode('utf-8')
    except NameError:
        pass
    compact = str(value).strip().lower().replace(' ', '')
    if compact == 's,mises(avg:75%)':
        return 's,mises'
    if compact == 's':
        return 's,mises'
    if compact == 'u':
        return 'u,magnitude'
    return compact


class OdbFieldOutputSelector(AFXDialog):
    """Modal extended-selection list populated from one ODB Step."""

    def __init__(self, owner, field_names, selected_names,
                 apply_selector, step_name, frame_count,
                 scan_selector=None, scan_note=''):
        self._field_names = list(field_names)
        self._field_list = None

        AFXDialog.__init__(
            self, owner, 'Select ODB Field Outputs', 0,
            DECOR_RESIZE | DIALOG_ACTIONS_SEPARATOR | DIALOG_UNPOST_DESTROY)

        body = FXVerticalFrame(self, LAYOUT_FILL_X | LAYOUT_FILL_Y,
                               0, 0, 0, 0, 8, 8, 8, 8, 6, 6)
        FXLabel(
            body,
            _format_ui_text(
                'Available outputs in Step %s (%d Frames).',
                (step_name, frame_count)))
        FXLabel(
            body,
            'Drag to select a range; use Ctrl/Shift for extended selection.')
        FXLabel(body, 'Rows such as S, S11 or S, Mises select a component or invariant.')
        if scan_note:
            FXLabel(body, _afx_string(scan_note))

        self._field_list = FXList(
            body, 12, None, 0,
            LIST_EXTENDEDSELECT | LAYOUT_FILL_X | LAYOUT_FILL_Y)
        selected_keys = set(
            _field_output_request_key(value) for value in selected_names)
        for index, field_name in enumerate(self._field_names):
            self._field_list.appendItem(_afx_string(field_name))
            if _field_output_request_key(field_name) in selected_keys:
                self._field_list.selectItem(index)

        self.appendActionButton('Use Selected', owner, apply_selector)
        if scan_selector is not None:
            self.appendActionButton('Scan all Frames', owner, scan_selector)
        self.appendActionButton(self.CANCEL)

    def selected_field_outputs(self):
        selected = []
        for index, field_name in enumerate(self._field_names):
            try:
                if self._field_list.isItemSelected(index):
                    selected.append(field_name)
            except Exception:
                pass
        return selected


class ExportPlanDialog(AFXDialog):
    """Read-only confirmation table for the files about to be exported."""

    def __init__(self, owner, rows, confirm_selector, cancel_selector):
        self._rows = list(rows)
        AFXDialog.__init__(
            self, owner, 'Export plan', 0,
            DECOR_RESIZE | DIALOG_ACTIONS_SEPARATOR | DIALOG_UNPOST_DESTROY)

        body = FXVerticalFrame(self, LAYOUT_FILL_X | LAYOUT_FILL_Y,
                               0, 0, 0, 0, 8, 8, 8, 8, 6, 6)
        existing_count = len([row for row in self._rows
                              if row.get('exists', False)])
        if existing_count:
            summary = _format_ui_text(
                '%d image(s) will be exported. %d existing output(s) will be overwritten.',
                (len(self._rows), existing_count))
        else:
            summary = _format_ui_text(
                '%d image(s) will be exported. No existing output was found.',
                (len(self._rows),))
        FXLabel(body, summary)
        FXLabel(body,
                'Review the resolved Field / Step / Frame / View / filename list, '
                'then confirm Export.')

        table_frame = FXVerticalFrame(
            body, FRAME_SUNKEN | FRAME_THICK |
            LAYOUT_FILL_X | LAYOUT_FILL_Y,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        total_rows = len(self._rows) + 1
        visible_rows = min(14, total_rows)
        self._table = AFXTable(table_frame, visible_rows, 6,
                               total_rows, 6)
        self._table.setLeadingRows(1)
        self._table.setLeadingRowLabels(
            'No.\tField\tStep\tFrame\tViewport / View\tOutput file')
        try:
            self._table.showHorizontalGrid(True)
            self._table.showVerticalGrid(True)
            self._table.setColumnWidth(0, 42)
            self._table.setColumnWidth(1, 100)
            self._table.setColumnWidth(2, 150)
            self._table.setColumnWidth(3, 80)
            self._table.setColumnWidth(4, 180)
            self._table.setColumnWidth(5, 420)
        except Exception:
            pass

        for index, row in enumerate(self._rows):
            values = (
                str(index + 1),
                row.get('field', 'Current'),
                row.get('step', 'Current'),
                row.get('frame', 'Current'),
                '%s / %s' % (row.get('viewport', ''), row.get('view', '')),
                row.get('path', ''),
            )
            for column, value in enumerate(values):
                self._table.setItemText(index + 1, column,
                                        _afx_string(value))

        self.appendActionButton('Export', owner, confirm_selector)
        self.appendActionButton('Cancel', owner, cancel_selector)


def _fx_color_to_hex(color):
    """Convert an Abaqus FOX FXColor value to the kernel's #RRGGBB text."""
    try:
        red = FXREDVAL(color)
        green = FXGREENVAL(color)
        blue = FXBLUEVAL(color)
    except Exception:
        # FOX stores FXRGB(r,g,b) as r<<8 | g<<16 | b<<24 | alpha.  Keep a
        # fallback for Abaqus builds that do not export the FX*VAL helpers.
        value = int(color)
        red = (value >> 8) & 0xFF
        green = (value >> 16) & 0xFF
        blue = (value >> 24) & 0xFF
    return '#%02X%02X%02X' % (int(red), int(green), int(blue))


class ScientificFigureExporterDB(AFXDataDialog):

    [ID_PREVIEW, ID_EXPORT, ID_RESET, ID_BROWSE, ID_CLOSE, ID_SELECT_ALL,
     ID_CLEAR_VIEWS, ID_COMBO_ASPECT, ID_COMBO_MODE, ID_COMBO_SCOPE,
     ID_COMBO_SPECTRUM, ID_COMBO_RANGE, ID_COMBO_BACKGROUND, ID_COMBO_RENDER,
     ID_COMBO_EDGES, ID_COMBO_FORMAT, ID_COMBO_EXPORT_MODE, ID_COLOR_TOP,
     ID_COLOR_BOTTOM, ID_LIVE_PREVIEW_TOGGLE,
     ID_LIVE_PREVIEW_TIMER, ID_PRESET_JOURNAL,
     ID_PRESET_PRESENTATION, ID_COMBO_FRAME_MODE,
      ID_FIELD_SELECTION, ID_FIELD_SELECTION_APPLY,
      ID_FIELD_SELECTION_SCAN, ID_EXPORT_PLAN_CONFIRM,
      ID_EXPORT_PLAN_CANCEL, ID_UI_SCALE] = range(
          AFXDataDialog.ID_LAST, AFXDataDialog.ID_LAST + 30)

    def __init__(self, form):
        self.form = form
        self.dirDb = None
        self._combo_widgets = {}
        self._combo_keywords = {}
        self._combo_keyword_values = {}
        self._combo_canonical_values = {}
        self._pending_widgets = []
        self._odb_widgets = []
        self._contour_widgets = []
        self._manual_range_widgets = []
        self._palette_blocks = []
        self._palette_preview_row = None
        self._palette_preview_native_label = None
        self._background_color_widgets = []
        self._background_color_keywords = {}
        self._is_odb_context = False
        self._viewport_names = []
        self._viewport_status = None
        self._contour_status = None
        self._calculated_label = None
        self._custom_aspect_field = None
        self._publication_width_field = None
        self._dpi_field = None
        self._field_selector_dialog = None
        self._export_plan_dialog = None
        self._field_selection_summary = None
        self._batch_always_widgets = []
        self._frame_every_widgets = []
        self._frame_specified_widgets = []
        self._batch_status = None
        self._ui_scale_combo = None
        self._ui_font_targets = []
        self._ui_scale = 'compact'
        self._ui_scale_applied = None
        self._figure_preview_label = None
        self._figure_preview_status = None
        self._figure_preview_icon = None
        self._figure_preview_path = None
        self._retired_preview_icons = []
        self._preview_temp_dir = os.path.abspath(os.path.join(
            tempfile.gettempdir(), 'ScientificFigureExporter'))
        self._owned_preview_paths = {}
        self._owned_plan_paths = {}
        self._live_preview_enabled = True
        self._live_preview_dirty = False
        self._action_in_flight = False
        self._last_preview_signature = None

        # This dialog is cached by AFXForm.getFirstDialog(). Keep its Python/
        # C++ data object alive when Abaqus unposts it (for example, when the
        # title-bar X cancels the form), while releasing the native window
        # resources so the same dialog can be posted again safely.
        AFXDataDialog.__init__(self, form, 'Scientific Figure Exporter', 0,
                               DECOR_RESIZE | DIALOG_UNPOST_DESTROY)

        body = FXVerticalFrame(self, LAYOUT_FILL_X | LAYOUT_FILL_Y)

        content = FXHorizontalFrame(body, LAYOUT_FILL_X | LAYOUT_FILL_Y)
        self._tabs = FXTabBook(content, None, 0,
                               TABBOOK_NORMAL | LAYOUT_FILL_X | LAYOUT_FILL_Y)
        self._build_view_tab(self._tabs)
        self._build_contour_tab(self._tabs)
        self._build_output_tab(self._tabs)
        self._build_figure_preview_pane(content)

        footer = FXVerticalFrame(body, LAYOUT_FILL_X)
        try:
            FXHorizontalSeparator(footer, LAYOUT_FILL_X)
        except Exception:
            pass
        footer_row = FXHorizontalFrame(footer, LAYOUT_FILL_X)
        self._ui_scale_combo = AFXComboBox(
            footer_row, 14, 2, 'UI size:', self, self.ID_UI_SCALE,
            LAYOUT_LEFT)
        self._ui_scale_combo.appendItem('Compact')
        self._ui_scale_combo.appendItem('Standard')
        self._ui_scale_combo.setCurrentItem(0)
        self._footer_label = FXLabel(
            footer_row,
            'Author: sysu@Liu Renjie | Contact email: '
            'liurj6@mail2.sysu.edu.cn',
            None, JUSTIFY_LEFT | LAYOUT_FILL_X)
        try:
            self._footer_label.setFont(getAFXFont(FONT_SMALL))
        except Exception:
            pass

        self.appendActionButton('Preview', self, self.ID_PREVIEW)
        self.appendActionButton('Export', self, self.ID_EXPORT)
        self.appendActionButton('Reset', self, self.ID_RESET)
        self.appendActionButton('Close', self, self.ID_CLOSE)

        FXMAPFUNC(self, SEL_COMMAND, self.ID_PREVIEW,
                  ScientificFigureExporterDB.onCmdPreview)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_EXPORT,
                  ScientificFigureExporterDB.onCmdExport)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_RESET,
                  ScientificFigureExporterDB.onCmdReset)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_BROWSE,
                  ScientificFigureExporterDB.onCmdBrowse)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_CLOSE,
                  ScientificFigureExporterDB.onCmdClose)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_COLOR_TOP,
                  ScientificFigureExporterDB.onCmdColor)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_COLOR_BOTTOM,
                  ScientificFigureExporterDB.onCmdColor)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_PRESET_JOURNAL,
                  ScientificFigureExporterDB.onCmdJournalPreset)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_PRESET_PRESENTATION,
                  ScientificFigureExporterDB.onCmdPresentationPreset)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_FIELD_SELECTION,
                  ScientificFigureExporterDB.onCmdFieldSelection)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_FIELD_SELECTION_APPLY,
                  ScientificFigureExporterDB.onCmdApplyFieldSelection)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_FIELD_SELECTION_SCAN,
                  ScientificFigureExporterDB.onCmdScanAllFieldOutputs)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_EXPORT_PLAN_CONFIRM,
                  ScientificFigureExporterDB.onCmdConfirmExportPlan)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_EXPORT_PLAN_CANCEL,
                  ScientificFigureExporterDB.onCmdCancelExportPlan)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_UI_SCALE,
                  ScientificFigureExporterDB.onCmdUIScale)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_LIVE_PREVIEW_TOGGLE,
                  ScientificFigureExporterDB.onCmdToggleLivePreview)
        FXMAPFUNC(self, SEL_TIMEOUT, self.ID_LIVE_PREVIEW_TIMER,
                  ScientificFigureExporterDB.onTimeoutLivePreview)

        for combo_id in self._combo_widgets.keys():
            FXMAPFUNC(self, SEL_COMMAND, combo_id,
                      ScientificFigureExporterDB.onCmdCombo)

        self._set_odb_controls(False)
        self._update_background_widgets()
        self._update_calculated_size()
        self._last_preview_signature = self._preview_signature()
        self._capture_ui_fonts()
        self._apply_ui_scale(resize_window=False)

    # ------------------------------------------------------------------
    # Tab construction
    # ------------------------------------------------------------------
    def _build_view_tab(self, tabs):
        FXTabItem(tabs, 'View & Display', None, TAB_TOP_NORMAL)
        page = FXVerticalFrame(tabs,
                               FRAME_RAISED | FRAME_THICK |
                               LAYOUT_FILL_X | LAYOUT_FILL_Y)

        view_box = FXGroupBox(page, 'Views (multi-select)',
                              FRAME_GROOVE | LAYOUT_FILL_X)
        rows = (('Current', 'Iso', 'Front', 'Back'),
                ('Left', 'Right', 'Top', 'Bottom'))
        for row_names in rows:
            row = FXHorizontalFrame(view_box, LAYOUT_FILL_X)
            for name in row_names:
                kw = getattr(self.form, _VIEW_KEY_NAMES[name])
                FXCheckButton(row, name, kw, 0, CHECKBUTTON_NORMAL)

        button_row = FXHorizontalFrame(view_box, LAYOUT_FILL_X)
        FXButton(button_row, 'Select All', tgt=self, sel=self.ID_SELECT_ALL)
        FXButton(button_row, 'Clear', tgt=self, sel=self.ID_CLEAR_VIEWS)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_SELECT_ALL,
                  ScientificFigureExporterDB.onCmdSelectAll)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_CLEAR_VIEWS,
                  ScientificFigureExporterDB.onCmdClearViews)
        FXCheckButton(button_row, 'Auto Fit', self.form.autoFitKw, 0,
                      CHECKBUTTON_NORMAL)

        viewport_box = FXGroupBox(page, 'Viewports',
                                  FRAME_GROOVE | LAYOUT_FILL_X)
        self._add_combo(viewport_box, 'Scope:', self.form.viewportScopeKw,
                        ('Current viewport', 'All open viewports'),
                        self.ID_COMBO_SCOPE, 0, (0, 1))
        self._add_combo(viewport_box, 'Output layout:', self.form.exportModeKw,
                        ('Separate files', 'Combined canvas'),
                        self.ID_COMBO_EXPORT_MODE, 0, (0, 1))
        FXLabel(viewport_box,
                'Existing subplots: choose All open viewports + Combined canvas.\n'
                'Current viewport uses the live layout; multiple selected views\n'
                'become one panel per view.')
        self._viewport_status = FXLabel(
            viewport_box, 'Viewport query will refresh when the dialog opens.')

        batch_box = FXGroupBox(page, 'ODB batch export',
                               FRAME_GROOVE | LAYOUT_FILL_X)
        FXLabel(batch_box,
                'Choose variables detected in the selected ODB Step.\n'
                'Leave blank to keep the current output:')
        field_row = FXHorizontalFrame(batch_box, LAYOUT_FILL_X)
        field_button = FXButton(
            field_row, 'Choose Field Outputs...', tgt=self,
            sel=self.ID_FIELD_SELECTION)
        self._register_odb_widget(field_button)
        self._batch_always_widgets.append(field_button)
        self._field_selection_summary = FXLabel(
            field_row, 'No field filter (keep current output).', None,
            JUSTIFY_LEFT | LAYOUT_FILL_X)

        frame_row = FXHorizontalFrame(batch_box, LAYOUT_FILL_X)
        frame_combo = self._add_combo(
            frame_row, 'Frame selection:', self.form.frameSelectionKw,
            ('Current', 'First', 'Last', 'Every N', 'Specified'),
            self.ID_COMBO_FRAME_MODE, 0, (0, 1, 2, 3, 4))
        self._register_odb_widget(frame_combo)
        step_field = AFXTextField(
            frame_row, 18, 'Step (blank=current):',
            self.form.stepNameKw, 0)
        self._register_odb_widget(step_field)
        self._batch_always_widgets.extend([frame_combo, step_field])

        every_row = FXHorizontalFrame(batch_box, LAYOUT_FILL_X)
        every_field = AFXTextField(
            every_row, 10, 'Every N:', self.form.everyNKw, 0)
        self._register_odb_widget(every_field)
        self._frame_every_widgets.append(every_field)

        specified_row = FXHorizontalFrame(batch_box, LAYOUT_FILL_X)
        specified_field = AFXTextField(
            specified_row, 24, 'Frame indices (0-based):',
            self.form.specifiedFramesKw, 0)
        self._register_odb_widget(specified_field)
        self._frame_specified_widgets.append(specified_field)
        self._batch_status = FXLabel(
            batch_box,
            'Static batch only. Every N includes the final Frame.\n'
            'Preview shows the first field/frame combination.')

        display_box = FXGroupBox(page, 'Display policy',
                                 FRAME_GROOVE | LAYOUT_FILL_X)
        self._add_combo(display_box, 'Render style:',
                        self.form.renderStyleKw,
                        ('As Current', 'Shaded', 'Filled', 'Wireframe',
                         'Hidden'), self.ID_COMBO_RENDER, 0)
        self._add_combo(display_box, 'Visible edges:',
                        self.form.visibleEdgesKw,
                        ('As Current', 'All', 'Exterior', 'Feature', 'Free',
                         'None'), self.ID_COMBO_EDGES, 0)
        render_widget = self._combo_widgets[self.ID_COMBO_RENDER]
        edge_widget = self._combo_widgets[self.ID_COMBO_EDGES]
        self._register_odb_widget(render_widget)
        self._register_odb_widget(edge_widget)

        trans_row = FXHorizontalFrame(display_box, LAYOUT_FILL_X)
        trans_check = FXCheckButton(trans_row, 'Translucency',
                                    self.form.translucencyEnabledKw, 0,
                                    CHECKBUTTON_NORMAL)
        self._register_odb_widget(trans_check)
        slider = AFXSlider(
            trans_row, self.form.translucencyKw, 0,
            AFXSLIDER_INSIDE_BAR | AFXSLIDER_SHOW_VALUE | LAYOUT_FILL_X)
        try:
            slider.setRange(0, 100)
            slider.setMinLabelText('0%')
            slider.setMaxLabelText('100%')
        except Exception:
            pass
        self._register_odb_widget(slider)

        ann_box = FXGroupBox(page, 'Annotations',
                             FRAME_GROOVE | LAYOUT_FILL_X)
        ann_row1 = FXHorizontalFrame(ann_box, LAYOUT_FILL_X)
        for label, kw in (('Legend', self.form.legendKw),
                          ('Compass', self.form.compassKw),
                          ('Triad', self.form.triadKw)):
            widget = FXCheckButton(ann_row1, label, kw, 0,
                                   CHECKBUTTON_NORMAL)
            if label in ('Legend', 'Triad'):
                self._register_odb_widget(widget)
        ann_row2 = FXHorizontalFrame(ann_box, LAYOUT_FILL_X)
        for label, kw in (('Title block', self.form.titleBlockKw),
                          ('State block', self.form.stateBlockKw),
                          ('Text / arrows', self.form.textArrowsKw)):
            widget = FXCheckButton(ann_row2, label, kw, 0,
                                   CHECKBUTTON_NORMAL)
            if label in ('Title block', 'State block'):
                self._register_odb_widget(widget)
        FXLabel(ann_box, 'Legend/Triad/Title/State require ODB viewports.\n'
                'Compass and existing Text / arrows can be toggled in any\n'
                'viewport; the original annotation state is restored.')

    def _build_contour_tab(self, tabs):
        FXTabItem(tabs, 'Contour & Style', None, TAB_TOP_NORMAL)
        page = FXVerticalFrame(tabs,
                               FRAME_RAISED | FRAME_THICK |
                               LAYOUT_FILL_X | LAYOUT_FILL_Y)

        spectrum_box = FXGroupBox(page, 'Spectrum',
                                  FRAME_GROOVE | LAYOUT_FILL_X)
        self._add_combo(spectrum_box, 'Color map:', self.form.spectrumNameKw,
                        PALETTE_NAMES, self.ID_COMBO_SPECTRUM, 0)
        reverse = FXCheckButton(spectrum_box, 'Reverse spectrum',
                                self.form.reverseSpectrumKw, 0,
                                CHECKBUTTON_NORMAL)
        self._register_contour_widget(self._combo_widgets[self.ID_COMBO_SPECTRUM])
        self._register_contour_widget(reverse)
        self._contour_status = FXLabel(
            spectrum_box,
            'ODB contour controls are enabled when all target viewports\n'
            'are in an active contour plot.')
        preview_box = FXGroupBox(spectrum_box, 'Preview',
                                 FRAME_GROOVE | LAYOUT_FILL_X)
        self._build_palette_preview(preview_box, 'Abaqus Default')

        range_box = FXGroupBox(page, 'Contour range',
                               FRAME_GROOVE | LAYOUT_FILL_X)
        intervals = AFXVerticalAligner(range_box)
        intervals_field = AFXTextField(intervals, 10, 'Intervals:',
                                       self.form.intervalsKw, 0)
        self._register_contour_widget(intervals_field)
        self._add_combo(range_box, 'Range:', self.form.contourRangeKw,
                        ('Current', 'Auto', 'Manual'), self.ID_COMBO_RANGE, 0)
        range_widget = self._combo_widgets[self.ID_COMBO_RANGE]
        self._register_contour_widget(range_widget)
        manual_row = FXHorizontalFrame(range_box, LAYOUT_FILL_X)
        min_field = AFXTextField(manual_row, 12, 'Min:',
                                 self.form.manualMinKw, 0)
        max_field = AFXTextField(manual_row, 12, 'Max:',
                                 self.form.manualMaxKw, 0)
        self._register_contour_widget(min_field)
        self._register_contour_widget(max_field)
        self._manual_range_widgets = [min_field, max_field]

        bg_box = FXGroupBox(page, 'Viewport background',
                            FRAME_GROOVE | LAYOUT_FILL_X)
        self._add_combo(bg_box, 'Mode:', self.form.backgroundModeKw,
                        ('Current', 'Solid', 'Gradient',
                         'No viewport background'), self.ID_COMBO_BACKGROUND,
                        0, (0, 1, 2, 3))
        bg_row = FXHorizontalFrame(bg_box, LAYOUT_FILL_X)
        # Abaqus 2021 can crash when an AFXStringKeyword is passed as the
        # AFXColorButton message target.  Use the documented FXObject target
        # route and relay the native FXColor value to the keyword explicitly.
        top_button = AFXColorButton(bg_row, 'Top:', self, self.ID_COLOR_TOP)
        bottom_button = AFXColorButton(bg_row, 'Bottom:', self,
                                       self.ID_COLOR_BOTTOM)
        for button, keyword in ((top_button, self.form.backgroundTopKw),
                                (bottom_button,
                                 self.form.backgroundBottomKw)):
            try:
                r, g, b = _hex_rgb(keyword.getValue())
                button.setRGBA(FXRGB(r, g, b))
            except Exception:
                pass
        self._background_color_keywords = {
            self.ID_COLOR_TOP: self.form.backgroundTopKw,
            self.ID_COLOR_BOTTOM: self.form.backgroundBottomKw,
        }
        self._background_color_widgets = [top_button, bottom_button]
        FXLabel(bg_box, 'Solid uses Top; Gradient uses Top and Bottom.\n'
                'Preview applies temporarily; Export restores the original\n'
                'viewport/session background afterwards.')
        preset_row = FXHorizontalFrame(page, LAYOUT_FILL_X)
        preset_button = FXButton(preset_row, 'Journal light preset',
                                 tgt=self, sel=self.ID_PRESET_JOURNAL)
        preset_button2 = FXButton(preset_row, 'Presentation dark preset',
                                  tgt=self, sel=self.ID_PRESET_PRESENTATION)
        FXLabel(page, 'Presets set a solid background color; other figure '
                'settings are unchanged.')

    def _build_output_tab(self, tabs):
        FXTabItem(tabs, 'Output', None, TAB_TOP_NORMAL)
        page = FXVerticalFrame(tabs,
                               FRAME_RAISED | FRAME_THICK |
                               LAYOUT_FILL_X | LAYOUT_FILL_Y)

        size_box = FXGroupBox(page, 'Aspect and resolution',
                              FRAME_GROOVE | LAYOUT_FILL_X)
        self._add_combo(size_box, 'Aspect ratio:', self.form.aspectKw,
                        ('Current', '16:9', '3:2', '4:3', '1:1', 'Custom'),
                        self.ID_COMBO_ASPECT, 0)
        self._custom_aspect_field = AFXTextField(
            size_box, 12, 'Custom ratio (W:H):', self.form.customAspectKw, 0)
        self._custom_aspect_field.disable()
        FXCheckButton(size_box, 'Lock ratio', self.form.lockRatioKw, 0,
                      CHECKBUTTON_NORMAL)
        self._add_combo(size_box, 'Sizing mode:', self.form.resolutionModeKw,
                        ('Pixel size', 'Publication size'), self.ID_COMBO_MODE,
                        0, (0, 1))
        pixel_row = FXHorizontalFrame(size_box, LAYOUT_FILL_X)
        AFXTextField(pixel_row, 12, 'Width (px):', self.form.widthKw, 0)
        AFXTextField(pixel_row, 12, 'Height (px):', self.form.heightKw, 0)
        publication_row = FXHorizontalFrame(size_box, LAYOUT_FILL_X)
        self._publication_width_field = AFXTextField(
            publication_row, 12, 'Width (mm):', self.form.physicalWidthMmKw,
            0)
        self._dpi_field = AFXTextField(publication_row, 10, 'DPI:',
                                       self.form.dpiKw, 0)
        self._publication_width_field.disable()
        self._dpi_field.disable()
        self._calculated_label = FXLabel(size_box,
                                         'Calculated: 1600 x 1200 px')

        format_box = FXGroupBox(page, 'File format',
                                FRAME_GROOVE | LAYOUT_FILL_X)
        self._add_combo(format_box, 'Format:', self.form.formatNameKw,
                        ('PNG', 'JPG', 'TIFF', 'SVG'),
                        self.ID_COMBO_FORMAT, 0)
        FXLabel(format_box,
                'PNG, JPG, TIFF, and SVG are available. JPG uses the Windows\n'
                'encoder (quality 95); transparent areas become white. EPS\n'
                'is not exposed because its export did not return reliably.')

        output_box = FXGroupBox(page, 'File naming',
                                FRAME_GROOVE | LAYOUT_FILL_X)
        aligner = AFXVerticalAligner(output_box)
        dir_row = FXHorizontalFrame(aligner, LAYOUT_FILL_X)
        AFXTextField(dir_row, 24, 'Output directory:',
                     self.form.outputDirKw, 0)
        FXButton(dir_row, 'Browse...', tgt=self, sel=self.ID_BROWSE)
        AFXTextField(aligner, 16, 'Base name:', self.form.baseNameKw, 0)
        AFXTextField(aligner, 18, 'Naming template:',
                     self.form.namingTemplateKw, 0)
        FXLabel(output_box,
                'Fields: {name}, {field}, {step}, {frame}, {view}, {viewport}.\n'
                'Batch fields are inserted automatically; invalid Windows\n'
                'filename characters are sanitized.')

    def _build_figure_preview_pane(self, parent):
        pane = FXVerticalFrame(parent,
                               FRAME_GROOVE | LAYOUT_FIX_WIDTH |
                               LAYOUT_FILL_Y,
                               0, 0, 270, 0, 5, 5, 5, 5, 4, 4)
        preview_box = FXGroupBox(pane, 'Live figure preview',
                                 FRAME_GROOVE | LAYOUT_FILL_X |
                                 LAYOUT_FILL_Y)
        self._figure_preview_label = FXLabel(
            preview_box, 'Preview will appear here after the first render.',
            None, JUSTIFY_CENTER_X | JUSTIFY_CENTER_Y |
            LAYOUT_FIX_WIDTH | LAYOUT_FIX_HEIGHT,
            0, 0, 240, 180, 5, 5, 5, 5)
        self._figure_preview_status = FXLabel(
            preview_box, 'Waiting for the first preview...',
            None, JUSTIFY_LEFT | LAYOUT_FILL_X)
        self._live_preview_checkbox = FXCheckButton(
            preview_box, 'Auto-update preview', self,
            self.ID_LIVE_PREVIEW_TOGGLE, CHECKBUTTON_NORMAL)
        self._live_preview_checkbox.setCheck(TRUE)
        FXLabel(preview_box,
                'Automatically re-render the preview after settings change.')
        FXLabel(preview_box,
                'PNG thumbnail (max 240 x 180 px).\n'
                'Combined canvas shows all panels.\n'
                'Separate files show first selected view\n'
                'of first target viewport.\n'
                'For a batch, this is the first field/frame.')

    def _set_ui_text(self, widget, source, *args):
        if widget is None:
            return
        try:
            widget.setText(_format_ui_text(source, args))
        except Exception:
            pass

    def _capture_ui_fonts(self):
        """Capture native widget fonts before applying the compact preset."""
        targets = []
        visited = {}

        def visit(widget):
            if widget is None or id(widget) in visited:
                return
            visited[id(widget)] = True
            try:
                font = widget.getFont()
                if font is not None:
                    targets.append((widget, font))
            except Exception:
                pass
            try:
                count = int(widget.numChildren())
            except Exception:
                count = 0
            for index in range(count):
                try:
                    visit(widget.childAtIndex(index))
                except Exception:
                    pass

        visit(self)
        self._ui_font_targets = targets

    def _apply_ui_scale(self, resize_window=True):
        """Apply a small native-font density preset without changing globals."""
        compact = self._ui_scale == 'compact'
        try:
            compact_font = getAFXFont(FONT_SMALL)
        except Exception:
            compact_font = None
        for widget, original_font in self._ui_font_targets:
            try:
                if compact and compact_font is not None:
                    widget.setFont(compact_font)
                else:
                    widget.setFont(original_font)
            except Exception:
                pass
        try:
            self.recalc()
        except Exception:
            pass

        # The dialog remains DECOR_RESIZE, so the user can still drag it after
        # choosing a preset.  Keep the native height required by the current
        # content: capping it below that height makes the lower controls appear
        # collapsed until the user drags the window edge.
        if resize_window:
            try:
                default_width = int(self.getDefaultWidth())
                default_height = int(self.getDefaultHeight())
                if compact:
                    width_cap = 1120
                else:
                    width_cap = 1320
                width = min(default_width, width_cap)
                height = default_height
                if width > 0 and height > 0:
                    self.resize(width, height)
            except Exception:
                pass
        self._ui_scale_applied = self._ui_scale

    def onCmdUIScale(self, sender, sel, ptr):
        try:
            index = self._ui_scale_combo.getCurrentItem()
        except Exception:
            index = 0
        self._ui_scale = 'standard' if index == 1 else 'compact'
        self._apply_ui_scale(resize_window=True)
        return 1

    def _preview_signature(self):
        names = (
            'viewCurrentKw', 'viewIsoKw', 'viewFrontKw', 'viewBackKw',
            'viewLeftKw', 'viewRightKw', 'viewTopKw', 'viewBottomKw',
            'autoFitKw',
            'viewportScopeKw', 'exportModeKw',
            'renderStyleKw',
            'visibleEdgesKw', 'translucencyEnabledKw', 'translucencyKw',
            'legendKw', 'compassKw', 'triadKw', 'titleBlockKw',
            'stateBlockKw', 'textArrowsKw', 'spectrumNameKw',
            'reverseSpectrumKw', 'intervalsKw', 'contourRangeKw',
            'manualMinKw', 'manualMaxKw', 'backgroundModeKw',
            'backgroundTopKw', 'backgroundBottomKw', 'aspectKw',
            'customAspectKw', 'lockRatioKw', 'resolutionModeKw',
            'widthKw', 'heightKw', 'physicalWidthMmKw', 'dpiKw',
            'formatNameKw', 'outputDirKw', 'baseNameKw',
            'namingTemplateKw', 'fieldOutputsKw', 'customFieldOutputsKw',
            'stepNameKw', 'frameSelectionKw', 'everyNKw',
            'specifiedFramesKw')
        values = []
        for name in names:
            try:
                values.append(getattr(self.form, name).getValue())
            except Exception:
                values.append(None)
        return tuple(values)

    def _schedule_live_preview(self):
        if not self._live_preview_enabled:
            return 0
        self._live_preview_dirty = True
        if self._action_in_flight:
            return 1
        try:
            selector = MKUINT(self.ID_LIVE_PREVIEW_TIMER, SEL_TIMEOUT)
            # FOX timers use nanoseconds. Reusing this target/selector
            # reschedules the timer, providing a quiet-period debounce.
            getAFXApp().addTimeout(self, selector, 700000000)
            return 1
        except Exception:
            self._set_ui_text(
                self._figure_preview_status,
                'Automatic preview is unavailable; click Preview to update it.')
            return 0

    def _cancel_live_preview_timeout(self):
        try:
            selector = MKUINT(self.ID_LIVE_PREVIEW_TIMER, SEL_TIMEOUT)
            getAFXApp().removeTimeout(self, selector)
        except Exception:
            pass
        self._live_preview_dirty = False

    def onCmdToggleLivePreview(self, sender, sel, ptr):
        self._live_preview_enabled = bool(sender.getCheck())
        if self._live_preview_enabled:
            self._last_preview_signature = self._preview_signature()
            self._schedule_live_preview()
        else:
            self._live_preview_dirty = False
            self._set_ui_text(
                self._figure_preview_status,
                'Automatic preview paused. Click Preview to update.')
        return 1

    def onTimeoutLivePreview(self, sender, sel, ptr):
        if not self._live_preview_enabled or not self._live_preview_dirty:
            return 1
        if self._action_in_flight:
            return 1
        self._live_preview_dirty = False
        return self._issue_action('preview', automatic=True)

    def processUpdates(self):
        AFXDataDialog.processUpdates(self)
        signature = self._preview_signature()
        if signature != self._last_preview_signature:
            self._last_preview_signature = signature
            if self._live_preview_enabled:
                self._schedule_live_preview()

    # ------------------------------------------------------------------
    # Widget helpers and callbacks
    # ------------------------------------------------------------------
    def _disable(self, widget, except_values=()):
        # ``except_values`` is retained as a documentation hook for controls
        # with partially verified values. The FOX combo has no portable
        # per-item disable API, so a whole combo is disabled when necessary.
        if except_values:
            return
        try:
            widget.disable()
        except Exception:
            pass
        self._pending_widgets.append(widget)

    def _register_odb_widget(self, widget):
        self._odb_widgets.append(widget)
        try:
            widget.disable()
        except Exception:
            pass

    def _register_contour_widget(self, widget):
        self._register_odb_widget(widget)
        self._contour_widgets.append(widget)

    def _set_odb_controls(self, enabled, contour_enabled=False):
        self._is_odb_context = bool(enabled)
        self._is_contour_context = bool(enabled and contour_enabled)
        for widget in self._odb_widgets:
            try:
                if enabled:
                    widget.enable()
                else:
                    widget.disable()
            except Exception:
                pass
        self._update_contour_widgets()
        self._update_batch_widgets()
        if self._contour_status is not None:
            if self._is_contour_context:
                self._set_ui_text(
                    self._contour_status,
                    'ODB contour controls enabled for the target viewport(s).')
            elif self._is_odb_context:
                self._set_ui_text(
                    self._contour_status,
                    'Disabled: target viewport(s) display an ODB but are not '
                    'in a contour plot state.')
            else:
                self._set_ui_text(
                    self._contour_status,
                    'Disabled: target viewport(s) are not displaying a contour ODB.')

    def _update_contour_widgets(self):
        manual = (self.form.contourRangeKw.getValue() == 'Manual')
        for widget in self._contour_widgets:
            try:
                if self._is_contour_context:
                    widget.enable()
                else:
                    widget.disable()
            except Exception:
                pass
        for widget in self._manual_range_widgets:
            try:
                if self._is_contour_context and manual:
                    widget.enable()
                else:
                    widget.disable()
            except Exception:
                pass

    def _update_batch_widgets(self):
        try:
            mode = int(self.form.frameSelectionKw.getValue())
        except Exception:
            mode = 0
        for widget in self._batch_always_widgets:
            try:
                if self._is_odb_context:
                    widget.enable()
                else:
                    widget.disable()
            except Exception:
                pass
        for widget in self._frame_every_widgets:
            try:
                if self._is_odb_context and mode == 3:
                    widget.enable()
                else:
                    widget.disable()
            except Exception:
                pass
        for widget in self._frame_specified_widgets:
            try:
                if self._is_odb_context and mode == 4:
                    widget.enable()
                else:
                    widget.disable()
            except Exception:
                pass

    def _update_background_widgets(self):
        """Enable native color buttons only for modes that consume colors."""
        try:
            mode = int(self.form.backgroundModeKw.getValue())
        except Exception:
            mode = 0
        # A solid background consumes only the top color.  The bottom color is
        # meaningful only for a gradient; leaving it enabled in Solid made the
        # UI suggest that the value had an effect when Abaqus ignored it.
        enabled = (mode in (1, 2))
        for index, widget in enumerate(self._background_color_widgets):
            try:
                if enabled and (mode == 2 or index == 0):
                    widget.enable()
                else:
                    widget.disable()
            except Exception:
                pass

    def _add_combo(self, parent, label, keyword, values, combo_id,
                   default_index, keyword_values=None):
        combo = AFXComboBox(parent, 18, min(6, len(values)), label, self,
                            combo_id, LAYOUT_FILL_X)
        for value in values:
            combo.appendItem(value)
        combo.setCurrentItem(default_index)
        if values:
            if keyword_values is None:
                keyword.setValue(values[default_index])
            else:
                keyword.setValue(keyword_values[default_index])
        self._combo_widgets[combo_id] = combo
        self._combo_keywords[combo_id] = keyword
        self._combo_canonical_values[combo_id] = tuple(values)
        if keyword_values is not None:
            self._combo_keyword_values[combo_id] = keyword_values
        return combo

    def _build_palette_preview(self, parent, palette_name):
        self._palette_preview_native_label = FXLabel(
            parent, 'Native Abaqus spectrum', None,
            JUSTIFY_CENTER_X | LAYOUT_FILL_X)
        row = FXHorizontalFrame(parent, LAYOUT_FILL_X)
        self._palette_preview_row = row
        preview_colors = _palette_colors(palette_name)
        if not preview_colors:
            # Keep the five existing custom-palette slots available while the
            # truthful native-spectrum label is shown for Abaqus Default.
            preview_colors = ('#808080', '#808080', '#808080',
                              '#808080', '#808080')
        for color in preview_colors:
            block = FXLabel(row, '    ', None, LABEL_NORMAL | LAYOUT_FILL_X)
            r, g, b = _hex_rgb(color)
            try:
                block.setBackColor(FXRGB(r, g, b))
            except Exception:
                pass
            self._palette_blocks.append(block)
        self._update_palette_preview(palette_name)

    def _update_palette_preview(self, palette_name):
        colors = _palette_colors(palette_name)
        try:
            if colors:
                self._palette_preview_native_label.hide()
                self._palette_preview_row.show()
            else:
                self._palette_preview_row.hide()
                self._palette_preview_native_label.show()
        except Exception:
            pass
        for index, block in enumerate(self._palette_blocks):
            if index >= len(colors):
                break
            r, g, b = _hex_rgb(colors[index])
            try:
                block.setBackColor(FXRGB(r, g, b))
            except Exception:
                pass

    def onCmdCombo(self, sender, sel, ptr):
        combo_id = None
        # The sender is the most stable identifier across Abaqus FOX builds.
        for candidate_id, widget in self._combo_widgets.items():
            if widget == sender:
                combo_id = candidate_id
                break
        if combo_id is None:
            # FOX selectors reserve the low 16 bits for the widget id.  This
            # fallback keeps the callback usable when a proxy sender is used.
            candidate_id = sel & 0xFFFF
            if candidate_id in self._combo_widgets:
                combo_id = candidate_id
        combo = self._combo_widgets.get(combo_id)
        keyword = self._combo_keywords.get(combo_id)
        if combo is not None and keyword is not None:
            index = combo.getCurrentItem()
            if index >= 0:
                values = self._combo_keyword_values.get(combo_id)
                if values is None:
                    canonical = self._combo_canonical_values.get(combo_id, ())
                    if index < len(canonical):
                        keyword.setValue(canonical[index])
                else:
                    keyword.setValue(values[index])
        if combo_id == self.ID_COMBO_ASPECT:
            self._update_output_widgets()
        if combo_id == self.ID_COMBO_MODE:
            self._update_output_widgets()
        if combo_id == self.ID_COMBO_RANGE:
            self._update_contour_widgets()
        if combo_id == self.ID_COMBO_SPECTRUM and keyword is not None:
            self._update_palette_preview(keyword.getValue())
        if combo_id == self.ID_COMBO_BACKGROUND:
            self._update_background_widgets()
        if combo_id == self.ID_COMBO_SCOPE:
            self._refresh_viewports()
        if combo_id == self.ID_COMBO_FRAME_MODE:
            self._update_batch_widgets()
        self._update_calculated_size()
        return 1

    def onCmdFieldSelection(self, sender, sel, ptr):
        if not self._is_odb_context:
            self._set_ui_text(
                self._field_selection_summary,
                'Field selection requires a viewport displaying an ODB.')
            return 1

        return self._issue_field_catalog(False)

    def _issue_field_catalog(self, full_scan):
        """Use the existing asynchronous command route instead of GUI proxies."""
        if self._action_in_flight:
            self._set_ui_text(self._field_selection_summary,
                              'A command is running. Please wait.')
            return 1
        self._cancel_live_preview_timeout()
        path = os.path.join(self._preview_temp_dir,
                            'export_plan_%s.json' % uuid.uuid4().hex)
        if not self._track_owned_plan(path):
            return 1
        self.form.actionKw.setValue('fields_all' if full_scan else 'fields')
        self.form.planPathKw.setValue(path)
        self.form._pending_export_plan_path = path
        self.form._pending_field_catalog = True
        self._set_ui_text(self._field_selection_summary,
                          'Reading field components in the Abaqus kernel...')
        self._action_in_flight = True
        try:
            if not os.path.isdir(self._preview_temp_dir):
                os.makedirs(self._preview_temp_dir)
            self.form.issueCommands()
        except Exception as error:
            self._action_in_flight = False
            self.form._pending_export_plan_path = None
            self.form._pending_field_catalog = False
            self._remove_owned_plan(path)
            self._set_ui_text(self._field_selection_summary,
                              'Could not read Field Outputs: %s', error)
        return 1

    def _show_field_catalog_from_path(self, path):
        try:
            with open(path, 'rb') as stream:
                catalog = json.load(stream)
            # json.load returns Unicode strings in Python 2. Keep any selector
            # creation error visible instead of overwriting it with the count.
            self._update_field_selection_summary()
            self._open_field_selector(catalog['fields'], catalog['step'],
                                      catalog['frameCount'], catalog['note'])
        except Exception as error:
            self._set_ui_text(self._field_selection_summary,
                              'Could not read Field Outputs: %s', error)
        finally:
            self.form.planPathKw.setValue('')
            self._remove_owned_plan(path)

    def _selected_field_names(self):
        selected_names = []
        for keyword in (self.form.fieldOutputsKw,
                        self.form.customFieldOutputsKw):
            try:
                value = keyword.getValue()
            except Exception:
                value = ''
            try:
                if isinstance(value, unicode):
                    value = value.encode('utf-8')
            except NameError:
                pass
            for token in str(value).split('|'):
                token = token.strip()
                if token:
                    selected_names.append(token)
        return selected_names

    def _open_field_selector(self, field_names, step_name, frame_count,
                             scan_note):
        try:
            selector = OdbFieldOutputSelector(
                self, field_names, self._selected_field_names(),
                self.ID_FIELD_SELECTION_APPLY, step_name, frame_count,
                self.ID_FIELD_SELECTION_SCAN, scan_note)
            self._field_selector_dialog = selector
            selector.create()
            # The posted dialog can outlive this callback; keep its reference
            # until the user applies the selection or opens it again.
            selector.showModal(self)
        except Exception as error:
            self._field_selector_dialog = None
            self._set_ui_text(
                self._field_selection_summary,
                'Could not open the Field Output selector: %s', error)
        return 1

    def onCmdScanAllFieldOutputs(self, sender, sel, ptr):
        """Opt into the complete Step scan after the fast selector opens."""
        old_selector = self._field_selector_dialog
        if old_selector is not None:
            selected = old_selector.selected_field_outputs()
            self.form.fieldOutputsKw.setValue('|'.join(selected))
            self.form.customFieldOutputsKw.setValue('')
            old_selector.hide()
            self._field_selector_dialog = None
        return self._issue_field_catalog(True)

    def onCmdApplyFieldSelection(self, sender, sel, ptr):
        selector = self._field_selector_dialog
        if selector is None:
            return 1
        try:
            selected = selector.selected_field_outputs()
            field_text = '|'.join([str(value) for value in selected])
            self.form.fieldOutputsKw.setValue(field_text)
            self.form.customFieldOutputsKw.setValue('')
            self._update_field_selection_summary()
            selector.hide()
            self._field_selector_dialog = None
            self._schedule_live_preview()
        except Exception as error:
            self._set_ui_text(
                self._field_selection_summary,
                'Could not apply Field Output selection: %s', error)
        return 1

    def onCmdBrowse(self, sender, sel, ptr):
        if self.dirDb is None:
            self.dirDb = AFXFileSelectorDialog(
                self, 'Select a Directory',
                self.form.outputDirKw, None,
                AFXSELECTFILE_DIRECTORY)
            self.dirDb.create()
        self.dirDb.showModal()
        return 1

    def onCmdColor(self, sender, sel, ptr):
        color_id = sel & 0xFFFF
        keyword = self._background_color_keywords.get(color_id)
        if keyword is None:
            for candidate_id, widget in (
                    (self.ID_COLOR_TOP, self._background_color_widgets[0]),
                    (self.ID_COLOR_BOTTOM, self._background_color_widgets[1])):
                if widget == sender:
                    color_id = candidate_id
                    keyword = self._background_color_keywords.get(candidate_id)
                    break
        if keyword is not None:
            try:
                keyword.setValue(_fx_color_to_hex(sender.getRGBA()))
            except Exception as error:
                # Keep the native color dialog usable while leaving a visible
                # diagnostic in the Abaqus message/replay stream if a FOX
                # build changes the color payload type.
                print('SFE color callback warning: %s' % error)
        return 1

    def _set_background_preset(self, color):
        self.form.backgroundModeKw.setValue(1)
        self.form.backgroundTopKw.setValue(color)
        self.form.backgroundBottomKw.setValue(color)
        combo = self._combo_widgets.get(self.ID_COMBO_BACKGROUND)
        if combo is not None:
            combo.setCurrentItem(1)
        red, green, blue = _hex_rgb(color)
        for widget in self._background_color_widgets:
            try:
                widget.setRGBA(FXRGB(red, green, blue))
            except Exception:
                pass
        self._update_background_widgets()
        self._schedule_live_preview()
        return 1

    def onCmdJournalPreset(self, sender, sel, ptr):
        return self._set_background_preset('#FFFFFF')

    def onCmdPresentationPreset(self, sender, sel, ptr):
        return self._set_background_preset('#1E2937')

    def _owned_preview_key(self, path):
        """Return a key only for this plug-in's UUID-named temp PNGs."""
        try:
            full_path = os.path.abspath(path)
            if os.path.normcase(os.path.dirname(full_path)) != \
                    os.path.normcase(self._preview_temp_dir):
                return None
            filename = os.path.basename(full_path)
            if not filename.startswith('preview_') or \
                    not filename.endswith('.png'):
                return None
            token = filename[len('preview_'):-len('.png')]
            if len(token) != 32 or not all(
                    char in '0123456789abcdefABCDEF' for char in token):
                return None
            return os.path.normcase(full_path)
        except Exception:
            return None

    def _track_owned_preview(self, path):
        key = self._owned_preview_key(path)
        if key is None:
            return 0
        self._owned_preview_paths[key] = os.path.abspath(path)
        return 1

    def _remove_owned_preview(self, path):
        key = self._owned_preview_key(path)
        if key is None or key not in self._owned_preview_paths:
            return 0
        owned_path = self._owned_preview_paths[key]
        try:
            if os.path.isfile(owned_path):
                os.remove(owned_path)
            del self._owned_preview_paths[key]
            return 1
        except Exception:
            # Keep it registered so a later close/deactivate can retry.
            return 0

    def _cleanup_owned_previews(self, preserve_paths=()):
        preserve = []
        for path in preserve_paths:
            key = self._owned_preview_key(path)
            if key is not None:
                preserve.append(key)
        for key in list(self._owned_preview_paths.keys()):
            if key not in preserve:
                self._remove_owned_preview(self._owned_preview_paths[key])

    def _owned_plan_key(self, path):
        """Return a key only for this plug-in's UUID-named plan JSON files."""
        try:
            full_path = os.path.abspath(path)
            if os.path.normcase(os.path.dirname(full_path)) != \
                    os.path.normcase(self._preview_temp_dir):
                return None
            filename = os.path.basename(full_path)
            if not filename.startswith('export_plan_') or \
                    not filename.endswith('.json'):
                return None
            token = filename[len('export_plan_'):-len('.json')]
            if len(token) != 32 or not all(
                    char in '0123456789abcdefABCDEF' for char in token):
                return None
            return os.path.normcase(full_path)
        except Exception:
            return None

    def _track_owned_plan(self, path):
        key = self._owned_plan_key(path)
        if key is None:
            return 0
        self._owned_plan_paths[key] = os.path.abspath(path)
        return 1

    def _remove_owned_plan(self, path):
        key = self._owned_plan_key(path)
        if key is None or key not in self._owned_plan_paths:
            return 0
        owned_path = self._owned_plan_paths[key]
        try:
            if os.path.isfile(owned_path):
                os.remove(owned_path)
            del self._owned_plan_paths[key]
            return 1
        except Exception:
            return 0

    def _cleanup_owned_plans(self):
        for key in list(self._owned_plan_paths.keys()):
            self._remove_owned_plan(self._owned_plan_paths[key])

    def _release_figure_preview(self, preserve_path=None):
        """Detach the current icon before removing its backing temporary PNG."""
        icon = self._figure_preview_icon
        current_path = self._figure_preview_path
        retired_icons = list(self._retired_preview_icons)
        self._retired_preview_icons = []
        preserve = []
        if preserve_path:
            preserve.append(preserve_path)

        if icon is not None:
            detached = False
            try:
                self._figure_preview_label.setIcon(None)
                detached = True
            except Exception:
                pass
            if detached:
                self._figure_preview_icon = None
                self._figure_preview_path = None
                retired_icons.append((icon, current_path))
                self._set_ui_text(
                    self._figure_preview_label,
                    'Preview will appear here after the first render.')
                self._set_ui_text(
                    self._figure_preview_status,
                    'Waiting for the first preview...')
            elif current_path:
                # Keep the attached icon and its file when detaching fails.
                preserve.append(current_path)
        else:
            self._figure_preview_path = None
            if current_path:
                self._remove_owned_preview(current_path)

        for retired_icon, retired_path in retired_icons:
            try:
                retired_icon.destroy()
                if retired_path:
                    self._remove_owned_preview(retired_path)
            except Exception:
                if retired_path:
                    preserve.append(retired_path)
                self._retired_preview_icons.append(
                    (retired_icon, retired_path))

        self._cleanup_owned_previews(preserve)

    def _issue_action(self, action, automatic=False):
        """Set the action and issue the existing AFXGuiCommand."""
        if self._action_in_flight:
            self._set_ui_text(
                self._figure_preview_status,
                'A preview/export command is still running. Please wait.')
            return 1
        self.form.actionKw.setValue(action)
        preview_path = None
        if action == 'preview':
            preview_path = os.path.join(
                self._preview_temp_dir, 'preview_%s.png' % uuid.uuid4().hex)
            while os.path.exists(preview_path):
                preview_path = os.path.join(
                    self._preview_temp_dir,
                    'preview_%s.png' % uuid.uuid4().hex)
            self.form.previewPathKw.setValue(preview_path)
            self.form._pending_figure_preview_path = preview_path
            self._set_ui_text(
                self._figure_preview_status,
                'Rendering a PNG thumbnail from the current settings...')
        else:
            self.form._pending_figure_preview_path = None
        if not self.form.doCustomChecks(show_errors=not automatic):
            self.form._pending_figure_preview_path = None
            if action == 'preview' and not automatic:
                self._set_ui_text(
                    self._figure_preview_status,
                    'Preview not rendered: correct the invalid settings first.')
            return 1
        if preview_path and not self._track_owned_preview(preview_path):
            self.form._pending_figure_preview_path = None
            self._set_ui_text(
                self._figure_preview_status,
                'Could not prepare a safe temporary preview file.')
            return 1
        # This is the documented AFXForm route used by Abaqus plug-in
        # examples for a non-default action button.  It avoids relying on a
        # getPressedButtonId() method that Abaqus 2021 does not expose on
        # AFXDataDialog.
        self._action_in_flight = True
        try:
            self.form.issueCommands()
        except Exception as error:
            self._action_in_flight = False
            self.form._pending_figure_preview_path = None
            if action == 'preview':
                self._remove_owned_preview(preview_path)
                self._set_ui_text(
                    self._figure_preview_status,
                    'Could not display the preview image: %s', error)
            else:
                print('Scientific Figure Exporter command failed: %s' % error)
        return 1

    def _load_figure_preview(self, path):
        """Load the PNG produced by the kernel into the persistent side pane."""
        if not os.path.isfile(path):
            self._remove_owned_preview(path)
            self._set_ui_text(
                self._figure_preview_status,
                'No preview image was produced. Check the Abaqus Error Log.')
            return 0
        icon = None
        committed = False
        try:
            icon = afxCreatePNGIcon(path)
            if not icon:
                raise RuntimeError('Abaqus could not read the preview PNG.')
            # The dialog already exists when Preview is clicked.  Abaqus'
            # icon documentation requires creating an icon resource before
            # attaching it to an existing widget.
            icon.create()
            self._figure_preview_label.setIcon(icon)
            old_icon = self._figure_preview_icon
            old_path = self._figure_preview_path
            self._figure_preview_icon = icon
            self._figure_preview_path = os.path.abspath(path)
            committed = True
            icon = None
            self._set_ui_text(self._figure_preview_label, '')
            if old_icon is not None:
                old_icon_destroyed = False
                try:
                    old_icon.destroy()
                    old_icon_destroyed = True
                except Exception:
                    self._retired_preview_icons.append((old_icon, old_path))
                if old_icon_destroyed and old_path and \
                        os.path.abspath(old_path) != os.path.abspath(path):
                    self._remove_owned_preview(old_path)
            if int(self.form.exportModeKw.getValue()) == 1:
                self._set_ui_text(
                    self._figure_preview_status,
                    'Combined canvas thumbnail rendered.')
            else:
                selected = [name for name in _VIEW_NAMES
                            if self._view_value(name)]
                view_name = selected[0] if selected else 'Current'
                self._set_ui_text(
                    self._figure_preview_status,
                    'Preview rendered: %s view.', view_name)
            return 1
        except Exception as error:
            if not committed:
                icon_destroyed = icon is None
                if icon is not None:
                    try:
                        icon.destroy()
                        icon_destroyed = True
                    except Exception:
                        self._retired_preview_icons.append((icon, path))
                if icon_destroyed:
                    self._remove_owned_preview(path)
            self._set_ui_text(
                self._figure_preview_status,
                'Could not display the preview image: %s', error)
            return 0

    def onCmdPreview(self, sender, sel, ptr):
        return self._issue_action('preview')

    def _issue_export_plan(self):
        """Ask the Abaqus kernel to resolve the read-only export plan."""
        if self._action_in_flight:
            self._set_ui_text(
                self._figure_preview_status,
                'A preview/export command is still running. Please wait.')
            return 1
        self.form.actionKw.setValue('plan')
        if not self.form.doCustomChecks(show_errors=True):
            return 1
        try:
            if not os.path.isdir(self._preview_temp_dir):
                os.makedirs(self._preview_temp_dir)
            plan_path = os.path.join(
                self._preview_temp_dir,
                'export_plan_%s.json' % uuid.uuid4().hex)
            while os.path.exists(plan_path):
                plan_path = os.path.join(
                    self._preview_temp_dir,
                    'export_plan_%s.json' % uuid.uuid4().hex)
        except Exception as error:
            showAFXErrorDialog(getAFXApp().getAFXMainWindow(),
                               _afx_string(str(error)))
            return 1
        if not self._track_owned_plan(plan_path):
            showAFXErrorDialog(
                getAFXApp().getAFXMainWindow(),
                _afx_string('Could not prepare a safe export plan file.'))
            return 1
        self.form.planPathKw.setValue(plan_path)
        self.form._pending_export_plan_path = plan_path
        self._set_ui_text(
            self._figure_preview_status,
            'Preparing the export plan in the Abaqus kernel...')
        self._action_in_flight = True
        try:
            self.form.issueCommands()
        except Exception as error:
            self._action_in_flight = False
            self.form._pending_export_plan_path = None
            self.form.planPathKw.setValue('')
            self._remove_owned_plan(plan_path)
            showAFXErrorDialog(getAFXApp().getAFXMainWindow(),
                               _afx_string(str(error)))
        return 1

    def _show_export_plan_from_path(self, path):
        try:
            with open(path, 'rb') as stream:
                rows = json.load(stream)
            if not isinstance(rows, list) or not rows:
                raise ValueError('The export plan is empty.')
            dialog = ExportPlanDialog(
                self, rows, self.ID_EXPORT_PLAN_CONFIRM,
                self.ID_EXPORT_PLAN_CANCEL)
            self._export_plan_dialog = dialog
            dialog.create()
            dialog.showModal(self)
        except Exception as error:
            self._export_plan_dialog = None
            showAFXErrorDialog(getAFXApp().getAFXMainWindow(),
                               _afx_string(str(error)))
        finally:
            self.form.planPathKw.setValue('')
            self._remove_owned_plan(path)

    def _discard_export_plan_dialog(self):
        dialog = self._export_plan_dialog
        self._export_plan_dialog = None
        if dialog is not None:
            try:
                dialog.hide()
            except Exception:
                pass

    def onCmdExport(self, sender, sel, ptr):
        if self._action_in_flight:
            self._set_ui_text(
                self._figure_preview_status,
                'A preview/export command is still running. Please wait.')
            return 1
        self._discard_export_plan_dialog()
        return self._issue_export_plan()

    def onCmdConfirmExportPlan(self, sender, sel, ptr):
        self._discard_export_plan_dialog()
        return self._issue_action('export')

    def onCmdCancelExportPlan(self, sender, sel, ptr):
        self._discard_export_plan_dialog()
        return 1

    def onCmdReset(self, sender, sel, ptr):
        return self._issue_action('reset')

    def onCmdClose(self, sender, sel, ptr):
        self._discard_export_plan_dialog()
        self._cancel_live_preview_timeout()
        try:
            # This callback runs in the Abaqus GUI process.  Reset must be sent
            # through the kernel command route; importing the kernel module
            # here raises "abaqus module may only be imported...".
            sendCommand(
                "import scientificFigureExporter_kernel; "
                "scientificFigureExporter_kernel.exportFigures(action='reset')")
        except Exception:
            # Closing the dialog must remain possible even if a stale preview
            # state belongs to a viewport that the user closed meanwhile.
            pass
        # Hiding the window alone leaves this AFXForm active. In that state,
        # selecting the plug-in menu entry again may not post the dialog until
        # some other CAE context change deactivates the form. Cancel through
        # the form lifecycle so the menu entry can activate it again cleanly.
        self.form.cancel()
        return 1

    def _view_value(self, name):
        return getattr(self.form, _VIEW_KEY_NAMES[name]).getValue()

    def _set_views(self, value):
        for name in _VIEW_NAMES:
            getattr(self.form, _VIEW_KEY_NAMES[name]).setValue(value)

    def onCmdSelectAll(self, sender=None, sel=None, ptr=None):
        self._set_views(1)
        return 1

    def onCmdClearViews(self, sender=None, sel=None, ptr=None):
        self._set_views(0)
        return 1

    def _update_output_widgets(self):
        aspect = self.form.aspectKw.getValue()
        mode = self.form.resolutionModeKw.getValue()
        if aspect == 'Custom':
            self._custom_aspect_field.enable()
        else:
            self._custom_aspect_field.disable()
        if mode == 1:
            self._publication_width_field.enable()
            self._dpi_field.enable()
        else:
            self._publication_width_field.disable()
            self._dpi_field.disable()
        self._update_contour_widgets()

    def _update_calculated_size(self):
        if self._calculated_label is None:
            return
        try:
            width = int(self.form.widthKw.getValue())
            height = int(self.form.heightKw.getValue())
            if self.form.resolutionModeKw.getValue() == 1:
                width = int(round(float(self.form.physicalWidthMmKw.getValue()) /
                                  25.4 * float(self.form.dpiKw.getValue())))
            ratio = self._ratio_from_keywords(width, height)
            if self.form.lockRatioKw.getValue():
                height = int(round(float(width) / ratio))
            self._set_ui_text(self._calculated_label,
                              'Calculated: %s x %s px', width, height)
        except Exception:
            self._set_ui_text(self._calculated_label,
                              'Calculated: check dimensions')

    def _update_batch_status(self, kernel_session, current):
        if self._batch_status is None:
            return
        if not self._is_odb_context:
            self._set_ui_text(
                self._batch_status,
                'Static batch requires an ODB viewport. Step names and Frame '
                'indices are 0-based within the selected Step.')
            return
        try:
            viewport = kernel_session.viewports[current]
            odb = viewport.displayedObject
            step_names = list(odb.steps.keys())
            field_frame = tuple(viewport.odbDisplay.fieldFrame)
            step_name = step_names[int(field_frame[0])]
            frame_count = len(odb.steps[step_name].frames)
            self._set_ui_text(
                self._batch_status,
                'Current ODB: Step %s | Frame %d/%d. Blank Step = current; '
                'preview shows the first batch combination.',
                step_name, int(field_frame[1]), max(0, frame_count - 1))
        except Exception:
            self._set_ui_text(
                self._batch_status,
                'ODB detected. Enter an exact Step name or leave it blank for '
                'the current Step; Frame indices are 0-based.')

    def _update_field_selection_summary(self):
        if self._field_selection_summary is None:
            return
        selected = []
        seen = set()
        for keyword in (self.form.fieldOutputsKw,
                        self.form.customFieldOutputsKw):
            try:
                value = keyword.getValue()
            except Exception:
                value = ''
            try:
                if isinstance(value, unicode):
                    value = value.encode('utf-8')
            except NameError:
                pass
            for token in str(value).split('|'):
                token = token.strip()
                key = _field_output_request_key(token)
                if token and key not in seen:
                    seen.add(key)
                    selected.append(token)
        if selected:
            self._set_ui_text(
                self._field_selection_summary,
                '%d Field Output(s) selected.', len(selected))
        else:
            self._set_ui_text(
                self._field_selection_summary,
                'No field filter (keep current output).')

    def _ratio_from_keywords(self, width, height):
        name = self.form.aspectKw.getValue()
        ratios = {'16:9': 16.0 / 9.0, '3:2': 3.0 / 2.0,
                  '4:3': 4.0 / 3.0, '1:1': 1.0}
        if name in ratios:
            return ratios[name]
        if name == 'Custom':
            value = self.form.customAspectKw.getValue()
            parts = value.split(':')
            if len(parts) != 2:
                raise ValueError('Custom aspect ratio must be W:H.')
            return float(parts[0]) / float(parts[1])
        return float(width) / float(height)

    # ------------------------------------------------------------------
    # Abaqus dialog lifecycle
    # ------------------------------------------------------------------
    def hide(self):
        # The title-bar X can unpost this dialog without going through the
        # custom Close button. Never leave a FOX timer targeting a hidden
        # dialog that the form is retaining for its next activation.
        self._discard_export_plan_dialog()
        self._cancel_live_preview_timeout()
        self.form._deactivated = True
        plan_path = self.form._pending_export_plan_path
        self.form._pending_export_plan_path = None
        if plan_path:
            self._remove_owned_plan(plan_path)
        self._cleanup_owned_plans()
        self._release_figure_preview(
            preserve_path=self.form._pending_figure_preview_path)
        return AFXDataDialog.hide(self)

    def show(self):
        self.form._deactivated = False
        self.form.actionKw.setValue('export')
        self._refresh_viewports()
        self._update_output_widgets()
        self._update_calculated_size()
        self._update_field_selection_summary()
        AFXDataDialog.show(self)
        if not self._ui_font_targets:
            self._capture_ui_fonts()
        self._apply_ui_scale(resize_window=True)
        if self._live_preview_enabled:
            self._schedule_live_preview()

    def _refresh_viewports(self):
        try:
            from kernelAccess import session as kernel_session
            names = list(kernel_session.viewports.keys())
            names.sort()
            current = kernel_session.currentViewportName
            if current in names:
                names.remove(current)
                names.insert(0, current)
            self._viewport_names = names
            is_odb = False
            is_contour = False
            if current in kernel_session.viewports.keys():
                try:
                    current_viewport = kernel_session.viewports[current]
                    is_odb = _is_odb_display(current_viewport.displayedObject)
                    is_contour = _is_contour_viewport(current_viewport)
                except Exception:
                    is_odb = False
                    is_contour = False

            # Scope 1 is evaluated against the live viewport repository.  A
            # mixed Model/ODB set cannot safely share ODB-specific controls,
            # and a mixed contour/non-contour set cannot safely share contour
            # options, so the GUI disables only the affected controls.
            try:
                all_scope = int(self.form.viewportScopeKw.getValue()) == 1
            except Exception:
                all_scope = False
            target_names = names if all_scope else ([current] if current else [])
            target_odb = []
            target_contour = []
            for name in target_names:
                try:
                    target = kernel_session.viewports[name]
                    target_odb.append(_is_odb_display(target.displayedObject))
                    target_contour.append(_is_contour_viewport(target))
                except Exception:
                    target_odb.append(False)
                    target_contour.append(False)
            odb_enabled = bool(target_odb) and all(target_odb)
            contour_enabled = odb_enabled and bool(target_contour) and all(target_contour)
            self._set_odb_controls(odb_enabled, contour_enabled)
            self._update_batch_status(kernel_session, current)
            if names:
                self.form.viewportNamesKw.setValue('|'.join(names))
                if all_scope and target_odb and not all(target_odb):
                    odb_status = 'disabled (mixed Model/ODB targets)'
                elif odb_enabled:
                    odb_status = 'enabled'
                else:
                    odb_status = 'disabled (target is not displaying an ODB)'
                if all_scope and target_contour and odb_enabled and not all(target_contour):
                    contour_status = 'disabled (mixed contour/non-contour targets)'
                elif contour_enabled:
                    contour_status = 'enabled'
                else:
                    contour_status = 'disabled'
                self._set_ui_text(
                    self._viewport_status,
                    'Current: %s | Available: %s | ODB controls: %s | '
                    'Contour controls: %s', current, ', '.join(names),
                    odb_status, contour_status)
            else:
                self.form.viewportNamesKw.setValue('')
                self._set_ui_text(
                    self._viewport_status, 'No open Abaqus viewport found.')
        except Exception as error:
            # Do not make the GUI unusable when the kernel bridge is not ready
            # during plug-in construction. The kernel will validate again.
            self._viewport_names = []
            self._set_odb_controls(False, False)
            self.form.viewportNamesKw.setValue('')
            self._set_ui_text(self._viewport_status,
                              'Viewport query pending: %s', error)

class ScientificFigureExporterForm(AFXForm):

    def __init__(self, owner):
        AFXForm.__init__(self, owner)
        self._pending_figure_preview_path = None
        self._pending_export_plan_path = None
        self._pending_field_catalog = False
        self._deactivated = False

        self.cmd = AFXGuiCommand(self, 'exportFigures',
                                 'scientificFigureExporter_kernel')

        self.actionKw = AFXStringKeyword(self.cmd, 'action', TRUE)
        self.actionKw.setValue('export')

        for name in _VIEW_NAMES:
            attr = _VIEW_KEY_NAMES[name]
            kw = AFXBoolKeyword(self.cmd, attr[:-2],
                                AFXBoolKeyword.TRUE_FALSE, isRequired=1,
                                defaultValue=1 if name == 'Current' else 0)
            setattr(self, attr, kw)

        self.autoFitKw = AFXBoolKeyword(
            self.cmd, 'autoFit', AFXBoolKeyword.TRUE_FALSE, isRequired=1,
            defaultValue=0)
        self.viewportScopeKw = AFXIntKeyword(self.cmd, 'viewportScope', TRUE)
        self.viewportNamesKw = AFXStringKeyword(self.cmd, 'viewportNames', TRUE)
        self.exportModeKw = AFXIntKeyword(self.cmd, 'exportMode', TRUE)
        self.fieldOutputsKw = AFXStringKeyword(
            self.cmd, 'fieldOutputs', TRUE)
        self.customFieldOutputsKw = AFXStringKeyword(
            self.cmd, 'customFieldOutputs', TRUE)
        self.stepNameKw = AFXStringKeyword(self.cmd, 'stepName', TRUE)
        self.frameSelectionKw = AFXIntKeyword(
            self.cmd, 'frameSelection', TRUE)
        self.everyNKw = AFXIntKeyword(self.cmd, 'everyN', TRUE)
        self.specifiedFramesKw = AFXStringKeyword(
            self.cmd, 'specifiedFrames', TRUE)

        self.renderStyleKw = AFXStringKeyword(self.cmd, 'renderStyle', TRUE)
        self.visibleEdgesKw = AFXStringKeyword(self.cmd, 'visibleEdges', TRUE)
        self.translucencyEnabledKw = AFXBoolKeyword(
            self.cmd, 'translucencyEnabled', AFXBoolKeyword.TRUE_FALSE,
            isRequired=1, defaultValue=0)
        self.translucencyKw = AFXIntKeyword(self.cmd, 'translucency', TRUE)
        self.legendKw = AFXBoolKeyword(
            self.cmd, 'legend', AFXBoolKeyword.TRUE_FALSE, isRequired=1,
            defaultValue=0)
        self.compassKw = AFXBoolKeyword(
            self.cmd, 'compass', AFXBoolKeyword.TRUE_FALSE, isRequired=1,
            defaultValue=0)
        self.triadKw = AFXBoolKeyword(
            self.cmd, 'triad', AFXBoolKeyword.TRUE_FALSE, isRequired=1,
            defaultValue=0)
        self.titleBlockKw = AFXBoolKeyword(
            self.cmd, 'titleBlock', AFXBoolKeyword.TRUE_FALSE,
            isRequired=1, defaultValue=0)
        self.stateBlockKw = AFXBoolKeyword(
            self.cmd, 'stateBlock', AFXBoolKeyword.TRUE_FALSE,
            isRequired=1, defaultValue=0)
        self.textArrowsKw = AFXBoolKeyword(
            self.cmd, 'textArrows', AFXBoolKeyword.TRUE_FALSE,
            isRequired=1, defaultValue=0)

        self.spectrumNameKw = AFXStringKeyword(self.cmd, 'spectrumName', TRUE)
        self.reverseSpectrumKw = AFXBoolKeyword(
            self.cmd, 'reverseSpectrum', AFXBoolKeyword.TRUE_FALSE,
            isRequired=1, defaultValue=0)
        self.intervalsKw = AFXIntKeyword(self.cmd, 'intervals', TRUE)
        self.contourRangeKw = AFXStringKeyword(self.cmd, 'contourRange', TRUE)
        self.manualMinKw = AFXFloatKeyword(self.cmd, 'manualMin', TRUE)
        self.manualMaxKw = AFXFloatKeyword(self.cmd, 'manualMax', TRUE)
        self.backgroundModeKw = AFXIntKeyword(self.cmd, 'backgroundMode', TRUE)
        self.backgroundTopKw = AFXStringKeyword(self.cmd, 'backgroundTop', TRUE)
        self.backgroundBottomKw = AFXStringKeyword(self.cmd, 'backgroundBottom', TRUE)

        self.aspectKw = AFXStringKeyword(self.cmd, 'aspect', TRUE)
        self.customAspectKw = AFXStringKeyword(self.cmd, 'customAspect', TRUE)
        self.lockRatioKw = AFXBoolKeyword(
            self.cmd, 'lockRatio', AFXBoolKeyword.TRUE_FALSE, isRequired=1,
            defaultValue=0)
        self.resolutionModeKw = AFXIntKeyword(self.cmd, 'resolutionMode', TRUE)
        self.widthKw = AFXIntKeyword(self.cmd, 'width', TRUE)
        self.heightKw = AFXIntKeyword(self.cmd, 'height', TRUE)
        self.physicalWidthMmKw = AFXFloatKeyword(
            self.cmd, 'physicalWidthMm', TRUE)
        self.dpiKw = AFXIntKeyword(self.cmd, 'dpi', TRUE)
        self.formatNameKw = AFXStringKeyword(self.cmd, 'formatName', TRUE)
        self.outputDirKw = AFXStringKeyword(self.cmd, 'outputDir', TRUE)
        self.baseNameKw = AFXStringKeyword(self.cmd, 'baseName', TRUE)
        self.namingTemplateKw = AFXStringKeyword(
            self.cmd, 'namingTemplate', TRUE)
        self.previewPathKw = AFXStringKeyword(self.cmd, 'previewPath', TRUE)
        self.planPathKw = AFXStringKeyword(self.cmd, 'planPath', TRUE)

        self.viewportScopeKw.setValue(0)
        self.viewportNamesKw.setValue('')
        self.exportModeKw.setValue(0)
        self.fieldOutputsKw.setValue('')
        self.customFieldOutputsKw.setValue('')
        self.stepNameKw.setValue('')
        self.frameSelectionKw.setValue(0)
        self.everyNKw.setValue(1)
        self.specifiedFramesKw.setValue('0|5|10')
        self.renderStyleKw.setValue('As Current')
        self.visibleEdgesKw.setValue('As Current')
        self.translucencyKw.setValue(0)
        self.spectrumNameKw.setValue('Abaqus Default')
        self.intervalsKw.setValue(12)
        self.contourRangeKw.setValue('Current')
        self.manualMinKw.setValue(0.0)
        self.manualMaxKw.setValue(1.0)
        self.backgroundModeKw.setValue(0)
        self.backgroundTopKw.setValue('#FFFFFF')
        self.backgroundBottomKw.setValue('#FFFFFF')
        self.aspectKw.setValue('Current')
        self.customAspectKw.setValue('4:3')
        self.resolutionModeKw.setValue(0)
        self.widthKw.setValue(1600)
        self.heightKw.setValue(1200)
        self.physicalWidthMmKw.setValue(160.0)
        self.dpiKw.setValue(300)
        self.formatNameKw.setValue('PNG')
        default_output_dir = os.path.join(
            os.path.expanduser('~'), 'ScientificFigureExporter_Output')
        self.outputDirKw.setValue(default_output_dir)
        self.baseNameKw.setValue('scientific_figure')
        self.namingTemplateKw.setValue('{name}_{view}')
        self.previewPathKw.setValue(os.path.join(
            tempfile.gettempdir(), 'ScientificFigureExporter_preview.png'))
        self.planPathKw.setValue('')

    def getFirstDialog(self):
        if not hasattr(self, 'mainDB') or self.mainDB is None:
            self.mainDB = ScientificFigureExporterDB(self)
        return self.mainDB

    def deactivate(self):
        # The title-bar X deactivates an AFXForm. Stop the dialog-targeted
        # timer before the toolkit unposts the dialog; its native data object
        # is retained by DIALOG_UNPOST_DESTROY and reused on the next open.
        db = getattr(self, 'mainDB', None)
        self._deactivated = True
        if db is not None:
            db._cancel_live_preview_timeout()
            plan_path = self._pending_export_plan_path
            self._pending_export_plan_path = None
            if plan_path:
                db._remove_owned_plan(plan_path)
            db._release_figure_preview(
                preserve_path=self._pending_figure_preview_path)
        AFXForm.deactivate(self)

    def handleException(self, exc):
        """Release the action lock when the kernel command fails asynchronously."""
        preview_path = self._pending_figure_preview_path
        self._pending_figure_preview_path = None
        plan_path = self._pending_export_plan_path
        self._pending_export_plan_path = None
        self._pending_field_catalog = False
        db = getattr(self, 'mainDB', None)
        if db is not None:
            db._action_in_flight = False
            if preview_path:
                db._remove_owned_preview(preview_path)
            if plan_path:
                db._remove_owned_plan(plan_path)
        self.planPathKw.setValue('')
        return AFXForm.handleException(self, exc)

    def doCustomChecks(self, show_errors=True):
        """Validate the action already selected by the native button callback."""
        db = self.getFirstDialog()
        if self.actionKw.getValue() in ('reset', 'fields', 'fields_all'):
            return 1

        def reject(message):
            if show_errors:
                showAFXErrorDialog(
                    getAFXApp().getAFXMainWindow(),
                    _afx_string(message))
            else:
                db._set_ui_text(db._figure_preview_status, message)
            return 0

        selected = [name for name in _VIEW_NAMES if db._view_value(name)]
        if not selected:
            return reject('Select at least one view.')

        db._refresh_viewports()
        try:
            width = int(self.widthKw.getValue())
            height = int(self.heightKw.getValue())
            if width <= 0 or height <= 0:
                raise ValueError('Pixel width and height must be greater than zero.')
            if self.resolutionModeKw.getValue() == 1:
                if float(self.physicalWidthMmKw.getValue()) <= 0:
                    raise ValueError('Publication width must be greater than zero.')
                if int(self.dpiKw.getValue()) <= 0:
                    raise ValueError('DPI must be greater than zero.')
            ratio = db._ratio_from_keywords(width, height)
            if ratio <= 0:
                raise ValueError('Aspect ratio must be greater than zero.')
            if self.contourRangeKw.getValue() == 'Manual':
                if float(self.manualMinKw.getValue()) >= float(self.manualMaxKw.getValue()):
                    raise ValueError('Manual minimum must be less than maximum.')
            if (self.renderStyleKw.getValue() == 'Wireframe' and
                    self.visibleEdgesKw.getValue() == 'None'):
                raise ValueError('Wireframe cannot be combined with Visible edges = None.')
            if (self.renderStyleKw.getValue() == 'Wireframe' and
                    self.translucencyEnabledKw.getValue()):
                raise ValueError('Translucency is not available for Wireframe output.')
            if (int(self.exportModeKw.getValue()) == 1 and
                    int(self.viewportScopeKw.getValue()) == 1 and
                    len(selected) > 1):
                raise ValueError(
                    'Combined canvas with All open viewports supports one '
                    'selected view at a time. For multiple view presets, '
                    'choose Current viewport.')
            frame_mode = int(self.frameSelectionKw.getValue())
            if frame_mode not in (0, 1, 2, 3, 4):
                raise ValueError('Unknown Frame selection mode.')
            if frame_mode == 3 and int(self.everyNKw.getValue()) <= 0:
                raise ValueError('Every N Frames must be greater than zero.')
            if frame_mode == 4 and not self.specifiedFramesKw.getValue().strip():
                raise ValueError('Specify at least one Frame index.')
            batch_requested = bool(
                self.fieldOutputsKw.getValue().strip() or
                self.customFieldOutputsKw.getValue().strip() or
                self.stepNameKw.getValue().strip() or frame_mode != 0)
            if batch_requested and not db._is_odb_context:
                raise ValueError(
                    'Field/Frame batch export requires a viewport displaying '
                    'an ODB.')
        except Exception as error:
            return reject(str(error))

        db._update_calculated_size()
        return 1

    def doCustomTasks(self):
        """Update the GUI only after the kernel completed its render command."""
        preview_path = self._pending_figure_preview_path
        self._pending_figure_preview_path = None
        plan_path = self._pending_export_plan_path
        self._pending_export_plan_path = None
        field_catalog = self._pending_field_catalog
        self._pending_field_catalog = False
        db = self.getFirstDialog()
        db._action_in_flight = False
        if preview_path:
            if self._deactivated:
                db._remove_owned_preview(preview_path)
            else:
                db._load_figure_preview(preview_path)
        if plan_path:
            if self._deactivated:
                db._remove_owned_plan(plan_path)
            elif field_catalog:
                db._show_field_catalog_from_path(plan_path)
            else:
                db._show_export_plan_from_path(plan_path)
        AFXForm.doCustomTasks(self)
        if db._live_preview_enabled and db._live_preview_dirty:
            db._schedule_live_preview()
