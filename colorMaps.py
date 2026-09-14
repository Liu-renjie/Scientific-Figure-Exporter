# -*- coding: utf-8 -*-
"""Native Spectrum color definitions for Scientific Figure Exporter.

The palettes are stored as plain hexadecimal strings so the GUI preview and
the Abaqus Visualization Spectrum factory can use the same source.  They are
named ``*-like`` where the project deliberately does not claim a byte-for-byte
match to an external plotting package.
"""


PALETTE_NAMES = (
    'Abaqus Default',
    'Viridis-like',
    'Plasma-like',
    'Inferno-like',
    'Magma-like',
    'Turbo-like',
    'Cool-Warm',
    'Blue-White-Red',
    'Blackbody',
    'Grayscale',
    'High Contrast',
    'Blue-Cyan-Yellow-Red',
)


PALETTES = {
    'Viridis-like': (
        '#440154', '#3B528B', '#21918C', '#5EC962', '#FDE725'),
    'Plasma-like': (
        '#0D0887', '#7E03A8', '#CC4778', '#F89540', '#F0F921'),
    'Inferno-like': (
        '#000004', '#420A68', '#932667', '#DD513A', '#FCFFA4'),
    'Magma-like': (
        '#000004', '#3B0F70', '#8C2981', '#DE4968', '#FCFDBF'),
    'Turbo-like': (
        '#30123B', '#2C7BB6', '#00A6CA', '#FDE725', '#A50026'),
    'Cool-Warm': (
        '#3B4CC0', '#7EA1FA', '#DDE318', '#F4987A', '#B40426'),
    'Blue-White-Red': (
        '#2166AC', '#67A9CF', '#F7F7F7', '#EF8A62', '#B2182B'),
    'Blackbody': (
        '#000000', '#4B0000', '#B22222', '#FF8C00', '#FFFACD'),
    'Grayscale': (
        '#000000', '#404040', '#808080', '#BFBFBF', '#FFFFFF'),
    'High Contrast': (
        '#000000', '#FFFFFF', '#D7191C', '#2C7BB6', '#FDAE61'),
    'Blue-Cyan-Yellow-Red': (
        '#0033A0', '#00A6D6', '#FDE725', '#F46D43', '#A50026'),
}

