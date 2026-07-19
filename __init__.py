# -*- coding: utf-8 -*-
"""QGIS entry point for 02Urban Portrait."""


def classFactory(iface):  # noqa: N802 - QGIS API
    from .main_plugin import O2UrbanPortraitPlugin

    return O2UrbanPortraitPlugin(iface)
