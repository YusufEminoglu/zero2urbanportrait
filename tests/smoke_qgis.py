"""QGIS runtime smoke checks for the 02Urban Portrait GUI and core helpers."""
from __future__ import annotations

import sys

from qgis.core import QgsApplication


application = QgsApplication([], False)
application.initQgis()

try:
    from zero2urbanportrait.core.presets import validate_preset
    from zero2urbanportrait.core.stipple import calculate_stipple_points
    from zero2urbanportrait.dialogs.dock import StepNodeWidget
    from zero2urbanportrait.dialogs.studio import UrbanPortraitDock

    stepper = StepNodeWidget()
    clicked: list[int] = []
    stepper.step_clicked.connect(clicked.append)
    stepper._step_buttons[2].click()
    assert clicked == [2]
    stepper.set_current_step(2)
    stepper.set_completed(0, True)
    assert stepper._current_step == 2
    assert stepper._step_completed[0]

    normalized = validate_preset("Smoke", {
        "colors": ["#111111", "#333333", "#555555", "#777777", "#999999"],
        "background": "#ffffff",
        "widths": [1.4, 1.0, 0.7, 0.4, 0.1],
    })
    assert len(normalized["colors"]) == 5

    points = calculate_stipple_points(
        0.0, 0.0, 10.0, 10.0, 3, 3, lambda _u, _v: 100, max_radius=1.0)
    assert points
    assert hasattr(UrbanPortraitDock, "_export_map")
    print("All QGIS GUI smoke checks passed.")
finally:
    application.exitQgis()

sys.exit(0)
