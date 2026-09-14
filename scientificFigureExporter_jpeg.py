# -*- coding: ascii -*-
"""Convert PNG output to JPEG with the Windows GDI+ encoder.

This module deliberately uses only Python's standard library and the Windows
GDI+ API so it remains compatible with Abaqus/CAE 2021 and embedded Python 2.7.
Transparent PNG pixels are composited over white because JPEG has no alpha.
"""

from __future__ import absolute_import

import ctypes
import os
import sys


_PIXEL_FORMAT_24BPP_RGB = 0x00021808
_JPEG_ENCODER_CLSID = '557CF401-1A04-11D3-9A73-0000F81EF32E'
_ENCODER_QUALITY_GUID = '1D5BE4B5-FA4A-452D-9CDD-5DB35105E7EB'


class _GdiplusStartupInput(ctypes.Structure):
    _fields_ = [
        ('GdiplusVersion', ctypes.c_uint),
        ('DebugEventCallback', ctypes.c_void_p),
        ('SuppressBackgroundThread', ctypes.c_int),
        ('SuppressExternalCodecs', ctypes.c_int),
    ]


class _GUID(ctypes.Structure):
    _fields_ = [
        ('Data1', ctypes.c_uint32),
        ('Data2', ctypes.c_uint16),
        ('Data3', ctypes.c_uint16),
        ('Data4', ctypes.c_ubyte * 8),
    ]


class _EncoderParameter(ctypes.Structure):
    _fields_ = [
        ('Guid', _GUID),
        ('NumberOfValues', ctypes.c_uint),
        ('Type', ctypes.c_uint),
        ('Value', ctypes.c_void_p),
    ]


class _EncoderParameters(ctypes.Structure):
    _fields_ = [
        ('Count', ctypes.c_uint),
        ('Parameter', _EncoderParameter * 1),
    ]


def _guid(value):
    parts = value.split('-')
    tail = ''.join(parts[3:])
    return _GUID(
        int(parts[0], 16), int(parts[1], 16), int(parts[2], 16),
        (ctypes.c_ubyte * 8)(*[int(tail[index:index + 2], 16)
                               for index in range(0, 16, 2)]))


def _unicode_path(path):
    try:
        unicode_type = unicode
    except NameError:
        unicode_type = str
    if isinstance(path, unicode_type):
        value = path
    else:
        encoding = sys.getfilesystemencoding() or 'mbcs'
        try:
            value = path.decode(encoding)
        except Exception:
            value = path.decode('mbcs')
    return os.path.abspath(value)


def is_available():
    """Return whether the Windows GDI+ library can be loaded."""
    if os.name != 'nt':
        return False
    try:
        ctypes.windll.gdiplus
        return True
    except Exception:
        return False


def _check_status(status, operation):
    if int(status) != 0:
        raise RuntimeError('Windows GDI+ %s failed with status %s.' %
                           (operation, status))


def _bind_gdiplus():
    if not is_available():
        raise RuntimeError('Windows GDI+ is not available for JPG conversion.')
    gdiplus = ctypes.windll.gdiplus
    gdiplus.GdiplusStartup.argtypes = [
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(_GdiplusStartupInput), ctypes.c_void_p]
    gdiplus.GdiplusStartup.restype = ctypes.c_int
    gdiplus.GdiplusShutdown.argtypes = [ctypes.c_size_t]
    gdiplus.GdiplusShutdown.restype = None
    gdiplus.GdipLoadImageFromFile.argtypes = [
        ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)]
    gdiplus.GdipLoadImageFromFile.restype = ctypes.c_int
    gdiplus.GdipGetImageWidth.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
    gdiplus.GdipGetImageWidth.restype = ctypes.c_int
    gdiplus.GdipGetImageHeight.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
    gdiplus.GdipGetImageHeight.restype = ctypes.c_int
    gdiplus.GdipCreateBitmapFromScan0.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    gdiplus.GdipCreateBitmapFromScan0.restype = ctypes.c_int
    gdiplus.GdipBitmapSetResolution.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float]
    gdiplus.GdipBitmapSetResolution.restype = ctypes.c_int
    gdiplus.GdipGetImageGraphicsContext.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    gdiplus.GdipGetImageGraphicsContext.restype = ctypes.c_int
    gdiplus.GdipGraphicsClear.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    gdiplus.GdipGraphicsClear.restype = ctypes.c_int
    gdiplus.GdipDrawImageI.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    gdiplus.GdipDrawImageI.restype = ctypes.c_int
    gdiplus.GdipDeleteGraphics.argtypes = [ctypes.c_void_p]
    gdiplus.GdipDeleteGraphics.restype = ctypes.c_int
    gdiplus.GdipSaveImageToFile.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(_GUID),
        ctypes.POINTER(_EncoderParameters)]
    gdiplus.GdipSaveImageToFile.restype = ctypes.c_int
    gdiplus.GdipDisposeImage.argtypes = [ctypes.c_void_p]
    gdiplus.GdipDisposeImage.restype = ctypes.c_int
    return gdiplus


def png_to_jpeg(png_path, jpeg_path, quality=95, resolution=0):
    """Convert a PNG to a JPEG, flattening transparency onto white.

    Args:
        png_path: Existing PNG file path.
        jpeg_path: Destination JPEG file path.
        quality: JPEG encoder quality from 0 through 100.
        resolution: Optional horizontal and vertical resolution in DPI.
    """
    quality = int(quality)
    if quality < 0 or quality > 100:
        raise ValueError('JPEG quality must be between 0 and 100.')
    source_path = _unicode_path(png_path)
    destination_path = _unicode_path(jpeg_path)
    if not os.path.isfile(source_path):
        raise IOError('PNG source file does not exist: %s' % source_path)

    gdiplus = _bind_gdiplus()
    token = ctypes.c_size_t(0)
    startup = _GdiplusStartupInput(1, None, 0, 0)
    _check_status(gdiplus.GdiplusStartup(
        ctypes.byref(token), ctypes.byref(startup), None), 'startup')

    source_image = ctypes.c_void_p()
    destination_image = ctypes.c_void_p()
    graphics = ctypes.c_void_p()
    try:
        _check_status(gdiplus.GdipLoadImageFromFile(
            source_path, ctypes.byref(source_image)), 'PNG load')
        width = ctypes.c_uint(0)
        height = ctypes.c_uint(0)
        _check_status(gdiplus.GdipGetImageWidth(
            source_image, ctypes.byref(width)), 'image width query')
        _check_status(gdiplus.GdipGetImageHeight(
            source_image, ctypes.byref(height)), 'image height query')
        if width.value <= 0 or height.value <= 0:
            raise RuntimeError('PNG image dimensions are invalid.')

        _check_status(gdiplus.GdipCreateBitmapFromScan0(
            int(width.value), int(height.value), 0,
            _PIXEL_FORMAT_24BPP_RGB, None,
            ctypes.byref(destination_image)), '24-bit bitmap creation')
        if float(resolution) > 0.0:
            _check_status(gdiplus.GdipBitmapSetResolution(
                destination_image, float(resolution), float(resolution)),
                'JPEG resolution setting')
        _check_status(gdiplus.GdipGetImageGraphicsContext(
            destination_image, ctypes.byref(graphics)),
            'bitmap graphics context creation')
        _check_status(gdiplus.GdipGraphicsClear(
            graphics, 0xFFFFFFFF), 'white background fill')
        _check_status(gdiplus.GdipDrawImageI(
            graphics, source_image, 0, 0), 'PNG drawing')
        _check_status(gdiplus.GdipDeleteGraphics(graphics),
                      'graphics context release')
        graphics = ctypes.c_void_p()

        quality_value = ctypes.c_ulong(quality)
        parameter = _EncoderParameter()
        parameter.Guid = _guid(_ENCODER_QUALITY_GUID)
        parameter.NumberOfValues = 1
        parameter.Type = 4
        parameter.Value = ctypes.cast(
            ctypes.pointer(quality_value), ctypes.c_void_p)
        parameters = _EncoderParameters()
        parameters.Count = 1
        parameters.Parameter[0] = parameter
        encoder = _guid(_JPEG_ENCODER_CLSID)
        _check_status(gdiplus.GdipSaveImageToFile(
            destination_image, destination_path, ctypes.byref(encoder),
            ctypes.byref(parameters)), 'JPEG save')

        if not os.path.isfile(destination_path):
            raise IOError('JPEG encoder returned without creating a file.')
        stream = open(destination_path, 'rb')
        try:
            signature = stream.read(2)
        finally:
            stream.close()
        if signature != b'\xff\xd8':
            raise IOError('GDI+ output does not have a JPEG signature.')
        return destination_path
    finally:
        if graphics.value:
            try:
                gdiplus.GdipDeleteGraphics(graphics)
            except Exception:
                pass
        if destination_image.value:
            try:
                gdiplus.GdipDisposeImage(destination_image)
            except Exception:
                pass
        if source_image.value:
            try:
                gdiplus.GdipDisposeImage(source_image)
            except Exception:
                pass
        gdiplus.GdiplusShutdown(token)
