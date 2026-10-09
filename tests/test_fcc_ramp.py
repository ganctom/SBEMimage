# -*- coding: utf-8 -*-

# ==============================================================================
#   This source file is part of SBEMimage (github.com/SBEMimage)
#   (c) 2018-2026 Friedrich Miescher Institute for Biomedical Research, Basel,
#   and the SBEMimage developers.
#   This software is licensed under the terms of the MIT License.
#   See LICENSE.txt in the project root folder.
# ==============================================================================

"""Unit tests for Focal Charge Compensation (FCC) ramp feature."""

import os
import sys
from configparser import ConfigParser
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from unittest.mock import MagicMock
for _mod in ['pythoncom', 'win32com', 'win32com.client', 'tqdm', 'mapfost']:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from config_template import (
    CFG_NUMBER_SECTIONS,
    CFG_NUMBER_KEYS,
    SYSCFG_NUMBER_SECTIONS,
    SYSCFG_NUMBER_KEYS,
    check_number_of_entries,
)
from sem_control_zeiss import SEM_SmartSEM


def test_config_number_of_entries():
    """Verify that default.ini and system.cfg have valid section and key counts."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src', 'default_cfg'))
    default_ini_path = os.path.join(base_dir, 'default.ini')
    system_cfg_path = os.path.join(base_dir, 'system.cfg')

    cfg = ConfigParser()
    with open(default_ini_path, 'r') as f:
        cfg.read_file(f)

    syscfg = ConfigParser()
    with open(system_cfg_path, 'r') as f:
        syscfg.read_file(f)

    assert check_number_of_entries(cfg, is_sys_cfg=False), (
        "default.ini entries count mismatch! "
        "sections: {}, expected: {}, keys: {}, expected: {}".format(
            len(cfg.sections()), CFG_NUMBER_SECTIONS,
            sum(len(cfg[s]) for s in cfg.sections()), CFG_NUMBER_KEYS
        )
    )

    assert check_number_of_entries(syscfg, is_sys_cfg=True), (
        "system.cfg entries count mismatch! "
        "sections: {}, expected: {}, keys: {}, expected: {}".format(
            len(syscfg.sections()), SYSCFG_NUMBER_SECTIONS,
            sum(len(syscfg[s]) for s in syscfg.sections()), SYSCFG_NUMBER_KEYS
        )
    )


def create_test_sem(initial_level=0.0, is_on=False):
    """Fixture to create a test SEM_SmartSEM instance with fake FCC primitives."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src', 'default_cfg'))
    cfg = ConfigParser()
    with open(os.path.join(base_dir, 'default.ini'), 'r') as f:
        cfg.read_file(f)
    syscfg = ConfigParser()
    with open(os.path.join(base_dir, 'system.cfg'), 'r') as f:
        syscfg.read_file(f)
    cfg['sys']['simulation_mode'] = 'True'
    sem = SEM_SmartSEM(cfg, syscfg)

    state = {
        'level': float(initial_level),
        'is_on': bool(is_on),
        'calls': []
    }

    sem.has_fcc = lambda: True
    sem.is_fcc_on = lambda: state['is_on']
    sem.is_fcc_off = lambda: not state['is_on']

    def fake_get_fcc_level():
        state['calls'].append(('get', state['level']))
        return state['level']

    def fake_set_fcc_level(val):
        state['calls'].append(('set', float(val)))
        state['level'] = float(val)
        return True

    def fake_turn_fcc_on():
        state['calls'].append(('turn_on',))
        state['is_on'] = True
        return True

    def fake_turn_fcc_off():
        state['calls'].append(('turn_off',))
        state['is_on'] = False
        return True

    sem.get_fcc_level = fake_get_fcc_level
    sem.set_fcc_level = fake_set_fcc_level
    sem.turn_fcc_on = fake_turn_fcc_on
    sem.turn_fcc_off = fake_turn_fcc_off

    return sem, state


def test_ramp_up_from_off_scenario_1():
    """Scenario 1: Ramp Up from OFF state (set 0 -> ON -> valve wait -> ramp to target)."""
    sem, state = create_test_sem(initial_level=10.0, is_on=False)
    sem.fcc_ramp_target = 30.0
    sem.fcc_ramp_duration_min = 5.0
    sem.fcc_ramp_valve_delay = 15.0

    t0 = 1000.0
    started, msg = sem.start_fcc_ramp_up(now=t0)
    assert started, msg
    assert sem.fcc_ramp_status[0] == 'VALVE_OPENING'
    assert state['is_on'] is True
    assert state['level'] == 0.0

    # Advance time within valve delay (e.g. 10 s)
    sem.fcc_ramp_tick(now=t0 + 10.0)
    assert sem.fcc_ramp_status[0] == 'VALVE_OPENING'

    # Advance time to valve delay deadline (15 s)
    sem.fcc_ramp_tick(now=t0 + 15.0)
    assert sem.fcc_ramp_status[0] == 'RAMPING'

    # Step through ramp duration (300 s) in 5 s intervals
    ramp_start = t0 + 15.0
    for tick in range(1, 61):
        t = ramp_start + tick * 5.0
        sem.fcc_ramp_tick(now=t)

    status = sem.fcc_ramp_status
    assert status[0] == 'IDLE'
    assert status[4] == 'FINISHED'
    assert state['level'] == 30.0


def test_ramp_down_with_auto_off_scenario_2():
    """Scenario 2: Ramp Down with Auto-OFF enabled (ramps to 0, waits valve delay, turns OFF)."""
    sem, state = create_test_sem(initial_level=30.0, is_on=True)
    sem.fcc_ramp_duration_min = 5.0
    sem.fcc_ramp_valve_delay = 15.0
    sem.fcc_ramp_auto_off = True

    t0 = 2000.0
    started, msg = sem.start_fcc_ramp_down(target=0.0, now=t0)
    assert started, msg
    assert sem.fcc_ramp_status[0] == 'RAMPING'

    # Ramp down to 0% over 300 s
    for tick in range(1, 61):
        sem.fcc_ramp_tick(now=t0 + tick * 5.0)

    # At 300 s, should reach 0.0 and transition to VALVE_CLOSING
    assert sem.fcc_ramp_status[0] == 'VALVE_CLOSING'
    assert state['level'] == 0.0
    assert state['is_on'] is True

    # Advance during valve closing wait
    sem.fcc_ramp_tick(now=t0 + 300.0 + 10.0)
    assert sem.fcc_ramp_status[0] == 'VALVE_CLOSING'
    assert state['is_on'] is True

    # Complete valve delay (15 s)
    sem.fcc_ramp_tick(now=t0 + 300.0 + 15.0)
    assert sem.fcc_ramp_status[0] == 'IDLE'
    assert sem.fcc_ramp_status[4] == 'FINISHED'
    assert state['is_on'] is False


def test_ramp_down_without_auto_off_scenario_3():
    """Scenario 3: Nominal Ramp Down to 0% with Auto-OFF disabled (remains ON at 0%)."""
    sem, state = create_test_sem(initial_level=20.0, is_on=True)
    sem.fcc_ramp_duration_min = 2.0  # 120 s
    sem.fcc_ramp_auto_off = False

    t0 = 3000.0
    started, msg = sem.start_fcc_ramp_down(target=0.0, now=t0)
    assert started, msg

    for tick in range(1, 25):
        sem.fcc_ramp_tick(now=t0 + tick * 5.0)

    assert sem.fcc_ramp_status[0] == 'IDLE'
    assert sem.fcc_ramp_status[4] == 'FINISHED'
    assert state['level'] == 0.0
    assert state['is_on'] is True


def test_stop_mid_flight_scenario_4():
    """Scenario 4: Stopping a ramp mid-flight leaves level and status intact."""
    sem, state = create_test_sem(initial_level=0.0, is_on=True)
    sem.fcc_ramp_target = 30.0
    sem.fcc_ramp_duration_min = 5.0

    t0 = 4000.0
    started, msg = sem.start_fcc_ramp_up(now=t0)
    assert started, msg

    # Ramp for 150 s (halfway)
    for tick in range(1, 31):
        sem.fcc_ramp_tick(now=t0 + tick * 5.0)

    current_level = state['level']
    assert 14.0 <= current_level <= 16.0

    sem.stop_fcc_ramp()
    assert sem.fcc_ramp_status[0] == 'IDLE'
    assert sem.fcc_ramp_status[4] == 'STOPPED'
    assert state['level'] == current_level


def test_external_interference_abort_scenario_5():
    """Scenario 5: External level change exceeding tolerance aborts the ramp."""
    sem, state = create_test_sem(initial_level=0.0, is_on=True)
    sem.fcc_ramp_target = 50.0
    sem.fcc_ramp_duration_min = 10.0

    t0 = 5000.0
    started, msg = sem.start_fcc_ramp_up(now=t0)
    assert started, msg

    # 1 tick
    sem.fcc_ramp_tick(now=t0 + 5.0)
    assert sem.fcc_ramp_status[0] == 'RAMPING'

    # Maliciously change level externally in SmartSEM beyond tolerance (1.0%)
    state['level'] = 90.0

    sem.fcc_ramp_tick(now=t0 + 10.0)
    assert sem.fcc_ramp_status[0] == 'IDLE'
    assert sem.fcc_ramp_status[4] == 'ABORTED_EXTERNAL'
    assert 'externally' in sem.fcc_ramp_status[5].lower()
    # Level must remain at the external level
    assert state['level'] == 90.0


def test_hardware_readback_error_scenario_7():
    """Scenario 7: Hardware readback error or exception aborts ramp."""
    sem, state = create_test_sem(initial_level=0.0, is_on=True)
    sem.fcc_ramp_target = 30.0
    sem.fcc_ramp_duration_min = 5.0

    t0 = 6000.0
    sem.start_fcc_ramp_up(now=t0)
    sem.fcc_ramp_tick(now=t0 + 5.0)

    # Return non-numeric level (simulating COM error returning "")
    sem.get_fcc_level = lambda: ""

    sem.fcc_ramp_tick(now=t0 + 10.0)
    assert sem.fcc_ramp_status[0] == 'IDLE'
    assert sem.fcc_ramp_status[4] == 'ABORTED_ERROR'


def test_ramp_up_already_at_or_above_target_scenario_8():
    """Scenario 8: Ramp Up refused when current level >= target."""
    sem, state = create_test_sem(initial_level=30.0, is_on=True)
    sem.fcc_ramp_target = 30.0

    started, msg = sem.start_fcc_ramp_up()
    assert started is False
    assert 'already at or above target' in msg.lower()
    assert sem.fcc_ramp_status[0] == 'IDLE'


def test_ramp_up_from_on_scenario_9():
    """Scenario 9: Ramp Up when already ON starts from current level with no valve wait."""
    sem, state = create_test_sem(initial_level=10.0, is_on=True)
    sem.fcc_ramp_target = 30.0
    sem.fcc_ramp_duration_min = 5.0

    t0 = 7000.0
    started, msg = sem.start_fcc_ramp_up(now=t0)
    assert started, msg
    assert sem.fcc_ramp_status[0] == 'RAMPING'
    assert state['level'] == 10.0


def test_ramp_down_refusal_at_or_below_target_scenario_10():
    """Scenario 10: Ramp Down refused when level <= target."""
    sem, state = create_test_sem(initial_level=0.0, is_on=True)
    started, msg = sem.start_fcc_ramp_down(target=0.0)
    assert started is False
    assert 'already at or below target' in msg.lower()


def test_ramp_down_from_on_scenario_11():
    """Scenario 11: Ramp Down when already ON starts directly from current level."""
    sem, state = create_test_sem(initial_level=25.0, is_on=True)
    started, msg = sem.start_fcc_ramp_down(target=0.0)
    assert started, msg
    assert sem.fcc_ramp_status[0] == 'RAMPING'


def test_stop_during_valve_waits_scenario_12():
    """Scenario 12: Stopping during valve waits leaves FCC ON at 0%."""
    # 12a: Stop during VALVE_OPENING
    sem, state = create_test_sem(initial_level=0.0, is_on=False)
    t0 = 7500.0
    sem.start_fcc_ramp_up(now=t0)
    assert sem.fcc_ramp_status[0] == 'VALVE_OPENING'
    sem.stop_fcc_ramp()
    assert sem.fcc_ramp_status[0] == 'IDLE'
    assert state['is_on'] is True
    assert state['level'] == 0.0

    # 12b: Stop during VALVE_CLOSING
    sem2, state2 = create_test_sem(initial_level=5.0, is_on=True)
    sem2.fcc_ramp_duration_min = 1.0  # 60 s
    sem2.fcc_ramp_auto_off = True
    t0 = 8000.0
    sem2.start_fcc_ramp_down(target=0.0, now=t0)
    for tick in range(1, 13):
        sem2.fcc_ramp_tick(now=t0 + tick * 5.0)
    assert sem2.fcc_ramp_status[0] == 'VALVE_CLOSING'
    sem2.stop_fcc_ramp()
    assert sem2.fcc_ramp_status[0] == 'IDLE'
    assert state2['is_on'] is True  # Auto-OFF cancelled


def test_external_off_aborts_ramp_scenario_13():
    """Scenario 13: FCC switched OFF externally during ramp aborts."""
    sem, state = create_test_sem(initial_level=10.0, is_on=True)
    sem.fcc_ramp_target = 30.0
    t0 = 9000.0
    sem.start_fcc_ramp_up(now=t0)
    sem.fcc_ramp_tick(now=t0 + 5.0)

    # Externally turned OFF
    state['is_on'] = False

    sem.fcc_ramp_tick(now=t0 + 10.0)
    assert sem.fcc_ramp_status[0] == 'IDLE'
    assert sem.fcc_ramp_status[4] == 'ABORTED_EXTERNAL'


def test_valve_fails_to_open_scenario_14():
    """Scenario 14: Valve fails to open (still reported OFF after delay)."""
    sem, state = create_test_sem(initial_level=0.0, is_on=False)
    t0 = 10000.0
    sem.start_fcc_ramp_up(now=t0)
    # Force is_on to False
    state['is_on'] = False

    sem.fcc_ramp_tick(now=t0 + sem.fcc_ramp_valve_delay + 1.0)
    assert sem.fcc_ramp_status[0] == 'IDLE'
    assert sem.fcc_ramp_status[4] == 'ABORTED_ERROR'


def test_auto_off_failure_scenario_15():
    """Scenario 15: Auto-OFF command fails, warns user that FCC remains ON at 0%."""
    sem, state = create_test_sem(initial_level=5.0, is_on=True)
    sem.fcc_ramp_duration_min = 1.0
    sem.fcc_ramp_auto_off = True
    t0 = 11000.0
    sem.start_fcc_ramp_down(target=0.0, now=t0)
    for tick in range(1, 13):
        sem.fcc_ramp_tick(now=t0 + tick * 5.0)
    assert sem.fcc_ramp_status[0] == 'VALVE_CLOSING'

    # Make turn_fcc_off fail to actually turn it off
    sem.turn_fcc_off = lambda: True  # does not change state['is_on']

    sem.fcc_ramp_tick(now=t0 + 60.0 + sem.fcc_ramp_valve_delay + 1.0)
    assert sem.fcc_ramp_status[0] == 'IDLE'
    assert sem.fcc_ramp_status[4] == 'AUTO_OFF_FAILED'
    assert state['is_on'] is True


def test_custom_ramp_down_target_scenario_18():
    """Scenario 18: Non-zero Ramp Down target stops at that target and does not turn OFF."""
    sem, state = create_test_sem(initial_level=30.0, is_on=True)
    sem.fcc_ramp_duration_min = 2.0  # 120 s
    sem.fcc_ramp_auto_off = True
    sem.fcc_ramp_down_target = 10.0

    t0 = 12000.0
    started, msg = sem.start_fcc_ramp_down(now=t0)
    assert started, msg

    for tick in range(1, 25):
        sem.fcc_ramp_tick(now=t0 + tick * 5.0)

    assert sem.fcc_ramp_status[0] == 'IDLE'
    assert sem.fcc_ramp_status[4] == 'FINISHED'
    assert state['level'] == 10.0
    assert state['is_on'] is True  # Auto-OFF only applies when target == 0.0


def test_linear_interpolation_granularity():
    """Verify linear interpolation yields 0.1 granularity steps without drift."""
    sem, state = create_test_sem(initial_level=29.0, is_on=True)
    sem.fcc_ramp_target = 30.0
    sem.fcc_ramp_duration_min = 5.0  # 300 s

    t0 = 13000.0
    started, msg = sem.start_fcc_ramp_up(now=t0)
    assert started, msg

    commanded_levels = [state['level']]
    for tick in range(1, 61):
        sem.fcc_ramp_tick(now=t0 + tick * 5.0)
        if state['level'] != commanded_levels[-1]:
            commanded_levels.append(state['level'])

    # Monotonically increasing
    for i in range(len(commanded_levels) - 1):
        assert commanded_levels[i] <= commanded_levels[i + 1]
        # Step size is multiple of 0.1
        diff = round(commanded_levels[i + 1] - commanded_levels[i], 2)
        assert diff == 0.1 or diff == 0.0

    assert state['level'] == 30.0


def test_fcc_dialog_ui_geometry_no_overlap():
    """Verify charge_compensator_settings_dlg.ui has all controls and no overlaps."""
    from PyQt5 import uic
    from PyQt5.QtWidgets import QApplication, QDialog
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    ui_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'gui', 'charge_compensator_settings_dlg.ui'))
    dlg = QDialog()
    uic.loadUi(ui_path, dlg)

    assert hasattr(dlg, 'pushButton_ramp_up')
    assert hasattr(dlg, 'pushButton_ramp_down')
    assert hasattr(dlg, 'toolButton_ramp_settings')
    assert hasattr(dlg, 'buttonBox')

    widgets = [
        dlg.label_text_fcc, dlg.pushButton_on, dlg.pushButton_off,
        dlg.label_text_vacuumPressure, dlg.lineEdit_vacuumPressure, dlg.comboBox_units,
        dlg.label_text_level, dlg.doubleSpinBox_level, dlg.horizontalSlider_level,
        dlg.pushButton_ramp_up, dlg.pushButton_ramp_down, dlg.toolButton_ramp_settings,
        dlg.buttonBox
    ]
    rects = [(w.objectName(), w.geometry()) for w in widgets]
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            name1, r1 = rects[i]
            name2, r2 = rects[j]
            intersection = r1.intersected(r2)
            assert intersection.isEmpty(), (
                "Widget overlap detected between {} ({}) and {} ({})!".format(
                    name1, r1.getRect(), name2, r2.getRect()
                )
            )


def test_fcc_ramp_settings_dlg_persistence_scenario_17(monkeypatch):
    """Scenario 17: FccRampSettingsDlg loads and persists settings."""
    from PyQt5.QtWidgets import QApplication
    from main_controls_dlg_windows import FccRampSettingsDlg

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    sem, state = create_test_sem(initial_level=0.0, is_on=False)
    sem.fcc_ramp_target = 30.0
    sem.fcc_ramp_duration_min = 5.0
    sem.fcc_ramp_valve_delay = 15.0
    sem.fcc_ramp_auto_off = True

    dlg = FccRampSettingsDlg(sem)
    assert dlg.label_target.text() == "Ramp Up target level (%):"
    assert dlg.label_duration.text() == "Ramp duration (min):"
    assert dlg.label_valve_delay.text() == "Valve settling delay (s):"
    assert dlg.doubleSpinBox_target.suffix() == ""
    assert dlg.spinBox_duration_min.suffix() == ""
    assert dlg.spinBox_valve_delay.suffix() == ""
    assert dlg.doubleSpinBox_target.width() == 70
    assert dlg.spinBox_duration_min.width() == 70
    assert dlg.spinBox_valve_delay.width() == 70
    assert dlg.width() == 280
    assert dlg.doubleSpinBox_target.value() == 30.0
    assert dlg.spinBox_duration_min.value() == 5
    assert dlg.spinBox_valve_delay.value() == 15
    assert dlg.checkBox_auto_off.isChecked() is True

    # Change settings
    dlg.doubleSpinBox_target.setValue(45.5)
    dlg.spinBox_duration_min.setValue(10)
    dlg.spinBox_valve_delay.setValue(30)
    dlg.checkBox_auto_off.setChecked(False)

    dlg.accept_settings()

    assert sem.fcc_ramp_target == 45.5
    assert sem.fcc_ramp_duration_min == 10.0
    assert sem.fcc_ramp_valve_delay == 30.0
    assert sem.fcc_ramp_auto_off is False
    assert sem.cfg['sem']['fcc_ramp_target'] == '45.5'
    assert sem.cfg['sem']['fcc_ramp_duration_min'] == '10.0'
    assert sem.cfg['sem']['fcc_ramp_valve_delay'] == '30.0'
    assert sem.cfg['sem']['fcc_ramp_auto_off'] == 'False'
    dlg.close()


def test_charge_compensator_dlg_ramp_ui_scenario_16():
    """Scenario 16: ChargeCompensatorDlg reflects live ramp states and allows stop."""
    from PyQt5.QtWidgets import QApplication
    from main_controls_dlg_windows import ChargeCompensatorDlg

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    sem, state = create_test_sem(initial_level=10.0, is_on=True)
    sem.fcc_ramp_target = 30.0
    sem.fcc_ramp_duration_min = 5.0

    dlg = ChargeCompensatorDlg(sem)
    assert dlg.pushButton_ramp_up.text() == 'Ramp Up'
    assert dlg.pushButton_ramp_down.text() == 'Ramp Down'
    assert dlg.pushButton_ramp_up.isEnabled() is True
    assert dlg.pushButton_ramp_down.isEnabled() is True
    assert dlg.toolButton_ramp_settings.isEnabled() is True

    # Start ramp up via dialog
    dlg.toggle_ramp_up()
    assert sem.fcc_ramp_status[0] == 'RAMPING'

    # Check that UI controls are now greyed out and button shows "Stop Ramp"
    dlg.update_ramp_ui()
    assert dlg.pushButton_ramp_up.text() == 'Stop Ramp'
    assert dlg.pushButton_ramp_up.isEnabled() is True
    assert dlg.pushButton_ramp_down.isEnabled() is False
    assert dlg.toolButton_ramp_settings.isEnabled() is False
    assert dlg.doubleSpinBox_level.isEnabled() is False
    assert dlg.horizontalSlider_level.isEnabled() is False
    assert dlg.pushButton_on.isEnabled() is False
    assert dlg.pushButton_off.isEnabled() is False

    # Stop ramp via dialog
    dlg.toggle_ramp_up()
    assert sem.fcc_ramp_status[0] == 'IDLE'
    assert sem.fcc_ramp_status[4] == 'STOPPED'

    # Check UI controls are restored
    dlg.update_ramp_ui()
    assert dlg.pushButton_ramp_up.text() == 'Ramp Up'
    assert dlg.pushButton_ramp_down.text() == 'Ramp Down'
    assert dlg.pushButton_ramp_up.isEnabled() is True
    assert dlg.pushButton_ramp_down.isEnabled() is True
    assert dlg.toolButton_ramp_settings.isEnabled() is True
    assert dlg.doubleSpinBox_level.isEnabled() is True
    assert dlg.horizontalSlider_level.isEnabled() is True
    dlg.close()


def test_fcc_button_styling_states():
    """Verify pushButton_FCC dynamic stylesheet across all ramp phases."""
    from unittest.mock import MagicMock
    if 'tqdm' not in sys.modules:
        sys.modules['tqdm'] = MagicMock()
    from PyQt5.QtWidgets import QApplication, QPushButton
    from main_controls import MainControls

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    btn = QPushButton('FCC')
    btn.setObjectName('pushButton_FCC')

    # Dummy object to test update_fcc_button_style
    class DummyMainControls:
        def __init__(self, button):
            self.pushButton_FCC = button
        update_fcc_button_style = MainControls.update_fcc_button_style

    dmc = DummyMainControls(btn)

    # 1. IDLE
    dmc.update_fcc_button_style('IDLE', None, 0.0)
    assert btn.styleSheet() == ''
    assert btn.toolTip() == ''

    # 2. VALVE_OPENING
    dmc.update_fcc_button_style('VALVE_OPENING', 'UP', 0.0)
    assert '#fff9c4' in btn.styleSheet()
    assert 'border: 1px solid #adadad' in btn.styleSheet()
    assert 'border-radius: 3px' in btn.styleSheet()
    assert 'Waiting for valve' in btn.toolTip()

    # 3. VALVE_CLOSING
    dmc.update_fcc_button_style('VALVE_CLOSING', 'DOWN', 1.0)
    assert '#ffd600' in btn.styleSheet()
    assert 'border: 1px solid #adadad' in btn.styleSheet()
    assert 'border-radius: 3px' in btn.styleSheet()
    assert 'Waiting for valve' in btn.toolTip()

    # 4. RAMPING UP
    dmc.update_fcc_button_style('RAMPING', 'UP', 0.25)
    assert 'qlineargradient' in btn.styleSheet()
    assert 'stop: 0.250 #ffd600' in btn.styleSheet()
    assert 'border: 1px solid #adadad' in btn.styleSheet()
    assert 'border-radius: 3px' in btn.styleSheet()
    assert '25%' in btn.toolTip()
    assert 'UP' in btn.toolTip()

    # 5. RAMPING DOWN (inversed fill: 1.0 - progress)
    dmc.update_fcc_button_style('RAMPING', 'DOWN', 0.25)
    assert 'qlineargradient' in btn.styleSheet()
    assert 'stop: 0.750 #ffd600' in btn.styleSheet()
    assert 'border: 1px solid #adadad' in btn.styleSheet()
    assert 'border-radius: 3px' in btn.styleSheet()
    assert '25%' in btn.toolTip()
    assert 'DOWN' in btn.toolTip()


def test_combined_exit_prompt_scenario_6(monkeypatch):
    """Scenario 6: Active ramp presents a single combined prompt in closeEvent."""
    from unittest.mock import MagicMock
    if 'tqdm' not in sys.modules:
        sys.modules['tqdm'] = MagicMock()
    from PyQt5.QtWidgets import QApplication, QMessageBox
    from main_controls import MainControls

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    sem, state = create_test_sem(initial_level=0.0, is_on=True)
    sem.start_fcc_ramp_up()
    assert sem.fcc_ramp_status[0] == 'RAMPING'

    mc = MagicMock()
    mc.busy = False
    mc.microtome = None
    mc.sem = sem
    mc.simulation_mode = True
    mc.plc_initialized = False
    mc.acq_notes_saved = True
    mc.acq = MagicMock()
    mc.acq.acq_paused = False
    mc.cfg_file = 'default.ini'
    mc.syscfg = {'device': {'sem': 'Unknown'}}
    mc.viewport = MagicMock()
    mc.fcc_ramp_timer = MagicMock()
    mc.fcc_ramp_timer.isActive.return_value = True
    mock_file = MagicMock()
    monkeypatch.setattr('builtins.open', lambda *args, **kwargs: mock_file)

    asked_message = []
    def fake_question(parent, title, text, buttons):
        asked_message.append(text)
        return QMessageBox.Yes

    monkeypatch.setattr('main_controls.QMessageBox.question', fake_question)

    event = MagicMock()
    MainControls.closeEvent(mc, event)

    assert len(asked_message) == 1
    assert 'An FCC ramp is active' in asked_message[0]
    assert sem.fcc_ramp_status[0] == 'IDLE'
    assert sem.fcc_ramp_status[4] == 'STOPPED'
    mc.fcc_ramp_timer.stop.assert_called_once()


def test_acq_settings_dlg_no_widget_overlaps():
    """Verify that checkBox_FccRampDown has zero overlap in both acq_settings_dlg UIs."""
    import xml.etree.ElementTree as ET

    for ui_rel in ['gui/acq_settings_dlg.ui', 'gui/acq_settings_dlg_mock.ui']:
        ui_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', ui_rel))
        tree = ET.parse(ui_path)
        rects = []
        for widget in tree.getroot().iter('widget'):
            if widget.get('name') in ['acqSettings']:
                continue
            geom = widget.find('./property[@name="geometry"]/rect')
            if geom is not None:
                name = widget.get('name')
                x = int(geom.find('x').text)
                y = int(geom.find('y').text)
                w = int(geom.find('width').text)
                h = int(geom.find('height').text)
                rects.append((name, x, y, w, h))

        for i in range(len(rects)):
            n1, x1, y1, w1, h1 = rects[i]
            if n1 == 'checkBox_FccRampDown':
                for j in range(len(rects)):
                    if i == j:
                        continue
                    n2, x2, y2, w2, h2 = rects[j]
                    overlap = not (x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1)
                    assert not overlap, '{0} overlaps with {1} in {2}!'.format(n1, n2, ui_rel)


def test_scenario_20_fcc_not_fitted(monkeypatch):
    """Scenario 20: FCC not fitted -> checkbox disabled and unchecked, cfg not overwritten."""
    from PyQt5.QtWidgets import QApplication
    from main_controls_dlg_windows import AcqSettingsDlg

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    mock_acq = MagicMock()
    mock_acq.base_dir = 'C:\\test'
    mock_acq.slice_thickness = 40
    mock_acq.slice_counter = 0
    mock_acq.total_z_diff = 0.0
    mock_acq.send_metadata = False
    mock_acq.eht_off_after_stack = False
    mock_acq.metadata_project_name = 'test'
    mock_acq.use_target_z_diff = False
    mock_acq.number_slices = 100
    mock_acq.target_z_diff = 4000.0
    mock_acq.fcc_ramp_down_after_stack = True  # User had True configured
    mock_acq.sem = MagicMock()
    mock_acq.sem.has_fcc.return_value = False  # Not fitted!

    notifications = MagicMock()
    notifications.metadata_server_url = 'http://localhost'
    notifications.metadata_server_admin_email = 'test@example.com'

    dlg = AcqSettingsDlg(mock_acq, notifications, use_microtome=True)
    assert not dlg.checkBox_FccRampDown.isEnabled()
    assert not dlg.checkBox_FccRampDown.isChecked()

    # Calling accept should NOT overwrite mock_acq.fcc_ramp_down_after_stack to False
    monkeypatch.setattr(dlg, 'slices_valid', lambda *args: True)
    dlg.accept()
    assert mock_acq.fcc_ramp_down_after_stack is True
    dlg.close()


def test_acq_settings_dlg_with_fcc_fitted(monkeypatch):
    """Acquisition settings dialog properly reflects and saves fcc_ramp_down_after_stack when FCC fitted."""
    from PyQt5.QtWidgets import QApplication
    from main_controls_dlg_windows import AcqSettingsDlg

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    mock_acq = MagicMock()
    mock_acq.base_dir = 'C:\\test'
    mock_acq.slice_thickness = 40
    mock_acq.slice_counter = 0
    mock_acq.total_z_diff = 0.0
    mock_acq.send_metadata = False
    mock_acq.eht_off_after_stack = False
    mock_acq.metadata_project_name = 'test'
    mock_acq.use_target_z_diff = False
    mock_acq.number_slices = 100
    mock_acq.target_z_diff = 4000.0
    mock_acq.fcc_ramp_down_after_stack = True
    mock_acq.sem = MagicMock()
    mock_acq.sem.has_fcc.return_value = True

    notifications = MagicMock()
    notifications.metadata_server_url = 'http://localhost'
    notifications.metadata_server_admin_email = 'test@example.com'

    dlg = AcqSettingsDlg(mock_acq, notifications, use_microtome=True)
    assert dlg.checkBox_FccRampDown.isEnabled()
    assert dlg.checkBox_FccRampDown.isChecked()

    dlg.checkBox_FccRampDown.setChecked(False)
    monkeypatch.setattr(dlg, 'slices_valid', lambda *args: True)
    dlg.accept()
    assert mock_acq.fcc_ramp_down_after_stack is False
    dlg.close()


def test_scenario_19_auto_fcc_ramp_down_at_stack_end(monkeypatch):
    """Scenario 19: Stack completes -> FCC ramp-down executes first -> EHT turned off."""
    from acquisition import Acquisition

    acq = Acquisition.__new__(Acquisition)
    call_order = []

    sem = MagicMock()
    sem.has_fcc.return_value = True
    sem.is_fcc_on.return_value = True
    sem.get_fcc_level.return_value = 30.0
    sem.fcc_ramp_down_target = 0.0

    status_states = ['RAMPING', 'IDLE']
    def fake_status():
        s = status_states.pop(0) if status_states else 'IDLE'
        return (s, 'DOWN', 0.5, 0.0, None, '')

    type(sem).fcc_ramp_status = property(lambda self: fake_status())

    def fake_start_fcc_ramp_down(target=None):
        call_order.append('start_ramp_down')
        return True, 'Started'

    def fake_turn_eht_off():
        call_order.append('turn_eht_off')

    sem.start_fcc_ramp_down = fake_start_fcc_ramp_down
    sem.turn_eht_off = fake_turn_eht_off

    acq.sem = sem
    acq.fcc_ramp_down_after_stack = True
    acq.eht_off_after_stack = True
    acq.stack_name = 'test_stack'
    acq.use_email_monitoring = False
    acq.add_to_main_log = MagicMock()
    acq.main_controls_trigger = MagicMock()
    acq.autofocus = MagicMock()
    acq.autofocus.afss_active = False

    monkeypatch.setattr('acquisition.sleep', lambda s: None)

    acq.handle_stack_completion()

    assert call_order == ['start_ramp_down', 'turn_eht_off']


def test_scenario_21_manual_ramp_interrupted_at_stack_end(monkeypatch):
    """Scenario 21: Active manual ramp is stopped before auto ramp-down begins."""
    from acquisition import Acquisition

    acq = Acquisition.__new__(Acquisition)
    call_order = []

    sem = MagicMock()
    sem.has_fcc.return_value = True

    status_states = ['RAMPING_UP', 'IDLE', 'RAMPING_DOWN', 'IDLE']
    def fake_status():
        s = status_states.pop(0) if status_states else 'IDLE'
        return (s, None, 0.5, 0.0, None, '')

    type(sem).fcc_ramp_status = property(lambda self: fake_status())

    def fake_stop_fcc_ramp():
        call_order.append('stop_fcc_ramp')

    def fake_start_fcc_ramp_down(target=None):
        call_order.append('start_fcc_ramp_down')
        return True, 'Started'

    sem.stop_fcc_ramp = fake_stop_fcc_ramp
    sem.start_fcc_ramp_down = fake_start_fcc_ramp_down
    sem.turn_eht_off = lambda: call_order.append('turn_eht_off')

    acq.sem = sem
    acq.fcc_ramp_down_after_stack = True
    acq.eht_off_after_stack = True
    acq.stack_name = 'test_stack'
    acq.use_email_monitoring = False
    acq.add_to_main_log = MagicMock()
    acq.main_controls_trigger = MagicMock()
    acq.autofocus = MagicMock()
    acq.autofocus.afss_active = False

    monkeypatch.setattr('acquisition.sleep', lambda s: None)

    acq.handle_stack_completion()

    assert call_order == ['stop_fcc_ramp', 'start_fcc_ramp_down', 'turn_eht_off']


def test_scenario_22_auto_ramp_down_failure_proceeds_to_turn_off_eht(monkeypatch):
    """Scenario 22: If auto ramp-down fails or is stopped, EHT is still turned off."""
    from acquisition import Acquisition

    acq = Acquisition.__new__(Acquisition)
    call_order = []

    sem = MagicMock()
    sem.has_fcc.return_value = True
    type(sem).fcc_ramp_status = property(lambda self: ('IDLE', None, 0.0, 0.0, 'ABORTED_ERROR', 'Valve failed'))

    def fake_start_fcc_ramp_down(target=None):
        call_order.append('start_fcc_ramp_down')
        return False, 'Failed to start'

    sem.start_fcc_ramp_down = fake_start_fcc_ramp_down
    sem.turn_eht_off = lambda: call_order.append('turn_eht_off')

    acq.sem = sem
    acq.fcc_ramp_down_after_stack = True
    acq.eht_off_after_stack = True
    acq.stack_name = 'test_stack'
    acq.use_email_monitoring = False
    acq.add_to_main_log = MagicMock()
    acq.main_controls_trigger = MagicMock()
    acq.autofocus = MagicMock()
    acq.autofocus.afss_active = False

    acq.handle_stack_completion()

    assert call_order == ['start_fcc_ramp_down', 'turn_eht_off']




def test_charge_compensator_dlg_button_styling():
    """Verify that during a ramp-up, only the ON button becomes green."""
    from main_controls_dlg_windows import ChargeCompensatorDlg
    from unittest.mock import MagicMock
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    mock_sem = MagicMock()
    mock_sem.is_fcc_on.return_value = True
    mock_sem.get_fcc_level.return_value = "10.0"
    mock_sem.get_chamber_pressure.return_value = 0.0
    mock_sem.fcc_ramp_status = ('RAMPING_UP', 'UP', 50, 100, '', '')
    
    dlg = ChargeCompensatorDlg(mock_sem)
    
    # Check gear settings button icon and text
    assert dlg.toolButton_ramp_settings.text() == ''
    assert not dlg.toolButton_ramp_settings.icon().isNull()

    # Check states during ramp up
    assert not dlg.pushButton_on.isEnabled()
    assert not dlg.pushButton_off.isEnabled()
    assert "background-color: lime" in dlg.pushButton_on.styleSheet()
    assert "background-color: lime" not in dlg.pushButton_off.styleSheet()
    
    # Change state to ramping down
    mock_sem.is_fcc_on.return_value = True
    mock_sem.fcc_ramp_status = ('RAMPING_DOWN', 'DOWN', 50, 0, '', '')
    dlg.update()
    
    assert not dlg.pushButton_on.isEnabled()
    assert not dlg.pushButton_off.isEnabled()
    assert "background-color: lime" in dlg.pushButton_on.styleSheet()
    assert "background-color: lime" not in dlg.pushButton_off.styleSheet()

    # Change state to OFF and IDLE
    mock_sem.is_fcc_on.return_value = False
    mock_sem.fcc_ramp_status = ('IDLE', 'NONE', 0, 0, '', '')
    dlg.update()
    
    assert dlg.pushButton_on.isEnabled()
    assert not dlg.pushButton_off.isEnabled()
    assert "background-color: lime" not in dlg.pushButton_on.styleSheet()
    assert "background-color: lime" in dlg.pushButton_off.styleSheet()


def test_charge_compensator_dlg_final_level_refresh():
    """Verify that upon transitioning from RAMPING to IDLE, ChargeCompensatorDlg fetches the final level."""
    from main_controls_dlg_windows import ChargeCompensatorDlg
    from unittest.mock import MagicMock
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    mock_sem = MagicMock()
    mock_sem.is_fcc_on.return_value = True
    mock_sem.get_fcc_level.return_value = "0.0"
    mock_sem.get_chamber_pressure.return_value = 0.0
    mock_sem.fcc_ramp_status = ('IDLE', 'NONE', 0, 0, '', '')
    
    dlg = ChargeCompensatorDlg(mock_sem)
    assert dlg.value == 0.0

    # Simulate active ramp at 29.9%
    mock_sem.fcc_ramp_status = ('RAMPING', 'UP', 99, 30, '', '')
    mock_sem.get_fcc_level.return_value = "29.9"
    dlg.update()
    assert dlg.value == 29.9
    assert dlg.doubleSpinBox_level.value() == 29.9
    assert dlg._was_ramping is True

    # Ramp completes: state transitions to IDLE, SmartSEM reaches exact target 30.0%
    mock_sem.fcc_ramp_status = ('IDLE', 'UP', 100, 30, 'FINISHED', '')
    mock_sem.get_fcc_level.return_value = "30.0"
    dlg.update()
    assert dlg.value == 30.0
    assert dlg.doubleSpinBox_level.value() == 30.0
    assert dlg._was_ramping is False
    dlg.close()
