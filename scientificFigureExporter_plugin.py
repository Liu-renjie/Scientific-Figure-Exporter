# -*- coding: utf-8 -*-
"""Abaqus/CAE plug-in loader for Scientific Figure Exporter."""

from abaqusGui import *
from abaqusConstants import ALL

from scientificFigureExporter_form import ScientificFigureExporterForm


toolset = getAFXApp().getAFXMainWindow().getPluginToolset()

toolset.registerGuiMenuButton(
    object=ScientificFigureExporterForm(toolset),
    buttonText='Scientific Figure Exporter...',
    kernelInitString='import scientificFigureExporter_kernel',
    version='0.2',
    author='Liu Renjie',
    applicableModules=ALL,
    description=('Multi-view Scientific Figure Exporter with Auto Fit, '
                 'annotation toggles, background presets, JPG output, and '
                 'static Field Output/Frame batch export.\n\n'
                 'Abaqus/CAE 2021 and Python 2.7 compatibility target.'),
    helpUrl='https://github.com/Liu-renjie/Scientific-Figure-Exporter')
