# -*- coding: utf-8 -*-

# ==============================================================================
#   This source file is part of SBEMimage (github.com/SBEMimage)
#   (c) 2018-2020 Friedrich Miescher Institute for Biomedical Research, Basel,
#   and the SBEMimage developers.
#   This software is licensed under the terms of the MIT License.
#   See LICENSE.txt in the project root folder.
# ==============================================================================

"""Tests for overview_manager.py"""

import sys
import pytest

# QApplication needed because QPixmap is used in overview_manager.py
from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)

# Use the default configuration for all tests
from test_load_config import config, sysconfig

from overview_manager import OverviewManager
from coordinate_system import CoordinateSystem
from sem_control import SEM

@pytest.fixture
def ov_manager():
    # Create CoordinateSystem instance
    cs = CoordinateSystem(config, sysconfig)
    # Create SEM (base class) instance
    sem = SEM(config, sysconfig)
    # Create and return GridManager instance
    return OverviewManager(config, sem, cs)

def test_initial_overview_config(ov_manager):
    assert ov_manager.number_ov == 1
    assert ov_manager.use_auto_debris_area

def test_create_new_overviews(ov_manager):
    ov_manager.add_new_overview()
    ov_manager.add_new_overview()
    assert ov_manager.number_ov == 3
    ov_manager.delete_overview()
    assert ov_manager.number_ov == 2

def test_overview_methods(ov_manager):
    ov_manager[0].centre_sx_sy = 0, 0
    ov_manager[0].rotation = 0
    width, height = ov_manager[0].width_d(), ov_manager[0].height_d()
    top_left_dx, top_left_dy, bottom_right_dx, bottom_right_dy = ov_manager[0].bounding_box()
    assert top_left_dx == -width / 2
    assert top_left_dy == -height / 2
    assert bottom_right_dx == width / 2
    assert bottom_right_dy == height / 2


def test_overview_rotation_config_persistence(ov_manager):
    cs = ov_manager.cs
    sem = ov_manager.sem
    ov_manager[0].rotation = 42.5
    ov_manager.save_to_cfg()
    assert config['overviews']['ov_rotation'] == '[42.5]'

    # Re-initialize overview manager and verify rotation is loaded
    reloaded_ovm = OverviewManager(config, sem, cs)
    assert reloaded_ovm[0].rotation == 42.5

    # Reset back to 0
    ov_manager[0].rotation = 0
    ov_manager.save_to_cfg()


def test_add_overview_with_rotation(ov_manager):
    ov_manager.add_new_overview(rotation=65.0)
    new_idx = ov_manager.number_ov - 1
    assert ov_manager[new_idx].rotation == 65.0
    ov_manager.delete_overview()


def test_bounding_box_unaffected_by_rotation(ov_manager):
    """Overview.bounding_box() returns unrotated bounds used as debris detection reference."""
    ov_manager[0].centre_sx_sy = 0, 0
    width, height = ov_manager[0].width_d(), ov_manager[0].height_d()

    for angle in [0, 45, 90, 180]:
        ov_manager[0].rotation = angle
        top_left_dx, top_left_dy, bottom_right_dx, bottom_right_dy = ov_manager[0].bounding_box()
        assert top_left_dx == -width / 2
        assert top_left_dy == -height / 2
        assert bottom_right_dx == width / 2
        assert bottom_right_dy == height / 2

    ov_manager[0].rotation = 0


