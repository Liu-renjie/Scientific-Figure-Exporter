# -*- coding: ascii -*-
"""Install Scientific Figure Exporter into the current user's Abaqus folder.

Compatible with Python 2.7 and Python 3. Uses only the standard library.
Run from the repository root, optionally passing a custom destination folder.
"""

from __future__ import print_function

import datetime
import os
import shutil
import sys


SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DESTINATION = os.path.join(
    os.path.expanduser('~'), 'abaqus_plugins', 'ScientificFigureExporter')
RUNTIME_FILES = (
    'scientificFigureExporter_plugin.py',
    'scientificFigureExporter_form.py',
    'scientificFigureExporter_kernel.py',
    'scientificFigureExporter_state.py',
    'scientificFigureExporter_jpeg.py',
    'colorMaps.py',
)


def install(destination=None):
    if destination is None:
        destination = DEFAULT_DESTINATION
    destination = os.path.abspath(destination)

    if os.path.normcase(destination) == os.path.normcase(SOURCE_DIR):
        raise RuntimeError('The install destination cannot be the repository root.')

    missing = [name for name in RUNTIME_FILES
               if not os.path.isfile(os.path.join(SOURCE_DIR, name))]
    if missing:
        raise RuntimeError('Missing runtime file(s): %s' % ', '.join(missing))

    if not os.path.isdir(destination):
        os.makedirs(destination)

    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    for name in RUNTIME_FILES:
        source = os.path.join(SOURCE_DIR, name)
        target = os.path.join(destination, name)
        if os.path.isfile(target):
            backup = target + '.bak_' + stamp
            shutil.copy2(target, backup)
            print('Backup: %s' % backup)
        shutil.copy2(source, target)
        print('Installed: %s' % target)

    print('Restart Abaqus/CAE to load the installed plug-in.')
    return destination


if __name__ == '__main__':
    target_dir = sys.argv[1] if len(sys.argv) > 1 else None
    install(target_dir)
