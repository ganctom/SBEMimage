# -*- coding: utf-8 -*-
"""
Tests for Viewport Approach Tab live per-tile updates and subpixel registered series display.
Validates AC-AA-FP-016 (and AC-SBEM-AUTO_APPROACH-009) and AC-AA-FP-017 (and AC-SBEM-AUTO_APPROACH-010).
"""

import os
import sys
import shutil
import tempfile
import unittest
from unittest import mock
from queue import Queue

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

for _mod in ['pythoncom', 'win32com', 'win32com.client', 'tqdm', 'mapfost']:
    if _mod not in sys.modules:
        sys.modules[_mod] = mock.MagicMock()

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QPoint, QRect, QPointF
from PyQt5.QtGui import QPixmap

from configparser import ConfigParser
from auto_approach import (
    ApproachProgress,
    ApproachState,
    ApproachStepRecord,
    AutoApproachConfig,
    AutoApproachEngine,
    TileStepEvaluation,
)
from viewport import Viewport
from coordinate_system import CoordinateSystem
from sem_control import SEM
from grid_manager import GridManager
from overview_manager import OverviewManager
from template_manager import TemplateManager
from imported_img import ImportedImages
import utils


def create_test_configs():
    """Load default session and system configurations for testing."""
    cfg = ConfigParser()
    cfg_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src', 'default_cfg', 'default.ini'))
    with open(cfg_path, 'r') as f:
        cfg.read_file(f)
    syscfg = ConfigParser()
    syscfg_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src', 'default_cfg', 'system.cfg'))
    with open(syscfg_path, 'r') as f:
        syscfg.read_file(f)
    cfg['sys']['simulation_mode'] = 'True'
    return cfg, syscfg


from test_auto_approach import MockStage


def build_test_viewport(test_dir):
    """Helper to instantiate an offscreen Viewport instance for testing."""
    app = QApplication.instance() or QApplication([])
    cfg, syscfg = create_test_configs()

    cs = CoordinateSystem(cfg, syscfg)
    cs.vp_width = 800
    cs.vp_height = 600

    sem = SEM(cfg, syscfg)
    gm = GridManager(cfg, sem, cs)
    stage = MockStage()
    ovm = OverviewManager(cfg, sem, cs)
    tm = TemplateManager(ovm)
    imported = ImportedImages(cfg)
    autofocus = mock.MagicMock()
    acq = mock.MagicMock()
    img_inspector = mock.MagicMock()
    mc_trigger = utils.Trigger()
    mc_trigger.queue = Queue()

    vp = Viewport(
        cfg, sem, stage, cs, ovm, gm, imported,
        autofocus, acq, img_inspector, mc_trigger, tm
    )
    vp.tabWidget.setCurrentIndex(3)
    return vp, app


class TestViewportApproachFeatures(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_vp_approach_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_ap_get_cumulative_shift_calculation(self):
        """AC-AA-FP-017: Cumulative shifts must accumulate pairwise shifts from Step 1 up to target step."""
        vp, _ = build_test_viewport(self.test_dir)

        # Baseline step 0 has 0 shift
        step0 = {
            'step_index': 0,
            'tile_evaluations': {
                '0.0': {'shift_yx_px': [0.0, 0.0]},
                '0.1': {'shift_yx_px': [0.0, 0.0]}
            }
        }
        # Step 1: shift (1.5, -2.0)
        step1 = {
            'step_index': 1,
            'tile_evaluations': {
                '0.0': {'shift_yx_px': [1.5, -2.0]},
                '0.1': {'shift_yx_px': [0.5, 1.0]}
            }
        }
        # Step 2: shift (-0.5, 3.0)
        step2 = {
            'step_index': 2,
            'tile_evaluations': {
                '0.0': {'shift_yx_px': [-0.5, 3.0]},
                '0.1': {'shift_yx_px': [1.0, -0.5]}
            }
        }
        # Step 3: shift (2.0, 0.5)
        step3 = {
            'step_index': 3,
            'tile_evaluations': {
                '0.0': {'shift_yx_px': [2.0, 0.5]},
                '0.1': {'shift_yx_px': [-1.0, 2.0]}
            }
        }
        vp.ap_steps = [step0, step1, step2, step3]

        # Step 0: zero shift
        self.assertEqual(vp.ap_get_cumulative_shift('0.0', 0), (0.0, 0.0))
        self.assertEqual(vp.ap_get_cumulative_shift('0.1', 0), (0.0, 0.0))

        # Step 1: shift of step 1
        self.assertEqual(vp.ap_get_cumulative_shift('0.0', 1), (1.5, -2.0))
        self.assertEqual(vp.ap_get_cumulative_shift('0.1', 1), (0.5, 1.0))

        # Step 2: step 1 + step 2
        self.assertAlmostEqual(vp.ap_get_cumulative_shift('0.0', 2)[0], 1.0)
        self.assertAlmostEqual(vp.ap_get_cumulative_shift('0.0', 2)[1], 1.0)
        self.assertAlmostEqual(vp.ap_get_cumulative_shift('0.1', 2)[0], 1.5)
        self.assertAlmostEqual(vp.ap_get_cumulative_shift('0.1', 2)[1], 0.5)

        # Step 3: step 1 + step 2 + step 3
        self.assertAlmostEqual(vp.ap_get_cumulative_shift('0.0', 3)[0], 3.0)
        self.assertAlmostEqual(vp.ap_get_cumulative_shift('0.0', 3)[1], 1.5)

    def test_ap_update_live_step_incremental_merge(self):
        """AC-AA-FP-016: Partial tile evaluations must merge in-place without creating duplicate step entries."""
        vp, _ = build_test_viewport(self.test_dir)
        vp.ap_steps = []

        prog_base = ApproachProgress(
            state='CALIBRATING_BASELINE', step_index=0, slices_cut_total=0,
            depth_removed_um=0.0, max_depth_um=10.0, current_batch_slice=0,
            batch_slices=5, triggered_tiles=[], run_dir=self.test_dir,
            message="Baseline: evaluated tile 0.0"
        )

        rec0_tile0 = {
            'step_index': 0,
            'tile_evaluations': {
                '0.0': {'raw_image_path': 'raw/step_000_t0.tif', 'shift_yx_px': [0.0, 0.0]}
            }
        }
        # First tile of baseline
        vp.ap_update_live_step(prog_base, rec0_tile0)
        self.assertEqual(len(vp.ap_steps), 1)
        self.assertIn('0.0', vp.ap_steps[0]['tile_evaluations'])
        self.assertNotIn('0.1', vp.ap_steps[0]['tile_evaluations'])
        self.assertEqual(vp.ap_current_step, 0)
        self.assertEqual(vp.ap_max_steps, 0)

        # Second tile of baseline: must merge into the same step 0!
        rec0_tile1 = {
            'step_index': 0,
            'tile_evaluations': {
                '0.1': {'raw_image_path': 'raw/step_000_t1.tif', 'shift_yx_px': [0.0, 0.0]}
            }
        }
        vp.ap_update_live_step(prog_base, rec0_tile1)
        self.assertEqual(len(vp.ap_steps), 1, "Must not append duplicate step 0")
        self.assertIn('0.0', vp.ap_steps[0]['tile_evaluations'])
        self.assertIn('0.1', vp.ap_steps[0]['tile_evaluations'])

        # Now Step 1 begins
        prog_step1 = ApproachProgress(
            state='EVALUATING', step_index=1, slices_cut_total=5,
            depth_removed_um=0.25, max_depth_um=10.0, current_batch_slice=0,
            batch_slices=5, triggered_tiles=[], run_dir=self.test_dir,
            message="Step 1: evaluated tile 0.0"
        )
        rec1_tile0 = {
            'step_index': 1,
            'depth_removed_um': 0.25,
            'tile_evaluations': {
                '0.0': {'raw_image_path': 'raw/step_001_t0.tif', 'shift_yx_px': [1.0, 0.5], 'dissimilarity': 0.12}
            }
        }
        vp.ap_update_live_step(prog_step1, rec1_tile0)
        self.assertEqual(len(vp.ap_steps), 2)
        self.assertEqual(vp.ap_current_step, 1)
        self.assertEqual(vp.ap_max_steps, 1)
        self.assertIn('0.0', vp.ap_steps[1]['tile_evaluations'])
        self.assertNotIn('0.1', vp.ap_steps[1]['tile_evaluations'])

        # Step 1, second tile arrives: merges into step 1
        rec1_tile1 = {
            'step_index': 1,
            'depth_removed_um': 0.25,
            'tile_evaluations': {
                '0.1': {'raw_image_path': 'raw/step_001_t1.tif', 'shift_yx_px': [-0.5, 1.2], 'dissimilarity': 0.08}
            }
        }
        vp.ap_update_live_step(prog_step1, rec1_tile1)
        self.assertEqual(len(vp.ap_steps), 2, "Must not append duplicate step 1")
        self.assertIn('0.0', vp.ap_steps[1]['tile_evaluations'])
        self.assertIn('0.1', vp.ap_steps[1]['tile_evaluations'])

    def test_ap_draw_registered_rendering(self):
        """AC-AA-FP-017: Canvas rendering with cumulative shifts succeeds in both Raw and Overlay modes."""
        vp, _ = build_test_viewport(self.test_dir)

        # Create synthetic images on disk
        raw_dir = os.path.join(self.test_dir, "raw")
        os.makedirs(raw_dir, exist_ok=True)
        img0_path = os.path.join(raw_dir, "step_000_t0.tif")
        img1_path = os.path.join(raw_dir, "step_001_t0.tif")

        arr0 = np.ones((100, 100), dtype=np.uint8) * 128
        arr1 = np.ones((100, 100), dtype=np.uint8) * 135
        Image.fromarray(arr0).save(img0_path)
        Image.fromarray(arr1).save(img1_path)

        vp.ap_run_dir = self.test_dir
        vp.ap_steps = [
            {
                'step_index': 0,
                'depth_removed_um': 0.0,
                'tile_evaluations': {
                    '0.0': {
                        'raw_image_path': img0_path,
                        'shift_yx_px': [0.0, 0.0],
                        'contact_detected': False
                    }
                }
            },
            {
                'step_index': 1,
                'depth_removed_um': 0.05,
                'tile_evaluations': {
                    '0.0': {
                        'raw_image_path': img1_path,
                        'shift_yx_px': [2.5, -3.2],
                        'dissimilarity': 0.15,
                        'contact_detected': False
                    }
                }
            }
        ]
        vp.ap_max_steps = 1
        vp.ap_current_step = 1

        # Test Raw mode
        vp.ap_raw_mode = True
        vp.ap_draw()
        self.assertFalse(vp.QLabel_ApproachCanvas.pixmap().isNull())
        self.assertIn('0.0', vp.ap_tile_raw_sizes)
        self.assertEqual(vp.ap_tile_raw_sizes['0.0'], (100, 100))

        # Test Overlay mode
        vp.ap_raw_mode = False
        vp.ap_draw()
        self.assertFalse(vp.QLabel_ApproachCanvas.pixmap().isNull())

    def test_engine_emits_per_tile_progress_events(self):
        """AC-AA-FP-016: Engine must emit progress notifications after each individual tile is evaluated."""
        from test_auto_approach import (
            MockSEM,
            MockMicrotome,
            MockTile,
            MockGrid,
            create_synthetic_tissue_pattern
        )

        pattern = create_synthetic_tissue_pattern(128, 128, seed=42).astype(np.uint8)
        sem = MockSEM(frame_generator=lambda: pattern)
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0)

        # Mock GridManager with 2 tiles: 0.0 and 0.1
        gm = mock.MagicMock()
        grid0 = MockGrid()
        grid0.tiles[0] = MockTile(sx_sy=(0.0, 0.0), tile_id=0)
        grid0.tiles[1] = MockTile(sx_sy=(10.0, 10.0), tile_id=1)
        gm.__getitem__.return_value = grid0

        cfg = AutoApproachConfig.from_cfg({
            'probe_tiles': '["0.0", "0.1"]',
            'batch_slices': 1,
            'max_depth_um': 0.1
        })

        callback_events = []

        def tracking_callback(prog, step_rec):
            # Record a snapshot of the progress and tile evaluations
            evals_snapshot = {}
            if step_rec is not None and hasattr(step_rec, 'tile_evaluations') and step_rec.tile_evaluations:
                evals_snapshot = dict(step_rec.tile_evaluations)
            callback_events.append((prog.state, prog.step_index, list(evals_snapshot.keys()), prog.message))

        engine = AutoApproachEngine(
            sem, microtome, stage, gm, cfg, self.test_dir,
            progress_callback=tracking_callback
        )
        res = engine.run()

        # Find all baseline events (step_index == 0) that have step records
        baseline_tile_events = [
            ev for ev in callback_events
            if ev[1] == 0 and len(ev[2]) > 0
        ]
        self.assertGreaterEqual(len(baseline_tile_events), 2)
        # First event should have only 1 tile
        self.assertEqual(len(baseline_tile_events[0][2]), 1)
        self.assertEqual(baseline_tile_events[0][2], ['0.0'])
        # Second event should have both tiles
        self.assertIn('0.0', baseline_tile_events[1][2])
        self.assertIn('0.1', baseline_tile_events[1][2])

        # Find all step 1 events (step_index == 1) that have step records
        step1_tile_events = [
            ev for ev in callback_events
            if ev[1] == 1 and len(ev[2]) > 0
        ]
        self.assertGreaterEqual(len(step1_tile_events), 2)
        # First event of step 1 has only 1 tile
        self.assertEqual(len(step1_tile_events[0][2]), 1)
        self.assertEqual(step1_tile_events[0][2], ['0.0'])
        # Second event of step 1 has both tiles
        self.assertIn('0.0', step1_tile_events[1][2])
        self.assertIn('0.1', step1_tile_events[1][2])

    def test_wheel_and_slider_navigation_registered_views(self):
        """AC-AA-FP-017: Wheel and slider navigation dynamically updates registered pixmaps."""
        from PyQt5.QtGui import QWheelEvent
        vp, _ = build_test_viewport(self.test_dir)

        raw_dir = os.path.join(self.test_dir, "raw")
        os.makedirs(raw_dir, exist_ok=True)
        img_paths = []
        for i in range(3):
            p = os.path.join(raw_dir, "step_%03d_t0.tif" % i)
            arr = np.ones((80, 80), dtype=np.uint8) * (120 + i * 10)
            Image.fromarray(arr).save(p)
            img_paths.append(p)

        vp.ap_run_dir = self.test_dir
        vp.ap_steps = [
            {'step_index': 0, 'depth_removed_um': 0.0, 'tile_evaluations': {'0.0': {'raw_image_path': img_paths[0], 'shift_yx_px': [0.0, 0.0]}}},
            {'step_index': 1, 'depth_removed_um': 0.05, 'tile_evaluations': {'0.0': {'raw_image_path': img_paths[1], 'shift_yx_px': [1.0, -1.5]}}},
            {'step_index': 2, 'depth_removed_um': 0.10, 'tile_evaluations': {'0.0': {'raw_image_path': img_paths[2], 'shift_yx_px': [-0.5, 2.0]}}},
        ]
        vp.ap_max_steps = 2
        vp.ap_current_step = 2
        vp.horizontalSlider_stepAP.setRange(0, 2)
        vp.horizontalSlider_stepAP.setValue(2)

        # Set step backward via ap_set_step
        vp.ap_set_step(1)
        self.assertEqual(vp.ap_current_step, 1)
        self.assertEqual(vp.horizontalSlider_stepAP.value(), 1)
        vp.ap_draw()
        self.assertFalse(vp.QLabel_ApproachCanvas.pixmap().isNull())

        # Wheel scroll event
        # delta > 0 scrolls forward, delta < 0 scrolls backward
        wheel_event_down = QWheelEvent(
            QPoint(100, 100), QPoint(100, 100), QPoint(0, 0),
            QPoint(0, -120), 0, Qt.Vertical, Qt.NoButton, Qt.NoModifier
        )
        vp.wheelEvent(wheel_event_down)
        self.assertEqual(vp.ap_current_step, 0)
        self.assertEqual(vp.horizontalSlider_stepAP.value(), 0)

        wheel_event_up = QWheelEvent(
            QPoint(100, 100), QPoint(100, 100), QPoint(0, 0),
            QPoint(0, 120), 0, Qt.Vertical, Qt.NoButton, Qt.NoModifier
        )
        vp.wheelEvent(wheel_event_up)
        self.assertEqual(vp.ap_current_step, 1)
        self.assertEqual(vp.horizontalSlider_stepAP.value(), 1)

    def test_ap_get_all_probe_tiles_canonical_sorting(self):
        """AC-AA-FP-016: Canonical sorting (grid, tile) across all sources."""
        vp, _ = build_test_viewport(self.test_dir)
        vp.ap_configured_tiles = ['1.2', '0.10']
        vp.ap_calibrations = {'0.1': {}}
        vp.gm.approach_ref_tiles = ['0.2']
        vp.ap_steps = [{'tile_evaluations': {'2.0': {}}}]

        all_tiles = vp.ap_get_all_probe_tiles()
        expected = ['0.1', '0.2', '0.10', '1.2', '2.0']
        self.assertEqual(all_tiles, expected)

    def test_ap_start_live_run_allocates_grid_immediately(self):
        """AC-AA-FP-016: ap_start_live_run sets configured tiles and immediately lays out grid."""
        vp, _ = build_test_viewport(self.test_dir)
        vp.ap_start_live_run(['0.0', '0.1', '0.2'])

        self.assertEqual(vp.ap_configured_tiles, ['0.0', '0.1', '0.2'])
        self.assertEqual(vp.ap_current_step, 0)
        self.assertEqual(vp.ap_max_steps, 0)
        self.assertEqual(len(vp.ap_steps), 0)

        # Ensure grid is allocated for all 3 tiles immediately
        self.assertEqual(len(vp.ap_tile_rects), 3)
        self.assertIn('0.0', vp.ap_tile_rects)
        self.assertIn('0.1', vp.ap_tile_rects)
        self.assertIn('0.2', vp.ap_tile_rects)

        # 3 tiles means 2 cols x 2 rows
        r0 = vp.ap_tile_rects['0.0']
        r1 = vp.ap_tile_rects['0.1']
        r2 = vp.ap_tile_rects['0.2']
        self.assertFalse(r0.intersects(r1))
        self.assertFalse(r0.intersects(r2))
        self.assertFalse(r1.intersects(r2))

    def test_ap_draw_fixed_grid_with_partial_evaluations_and_pending_badges(self):
        """AC-AA-FP-016: Canvas preserves multi-tile layout while tiles arrive incrementally."""
        vp, _ = build_test_viewport(self.test_dir)

        # Synthesize test images
        raw_dir = os.path.join(self.test_dir, "raw")
        os.makedirs(raw_dir, exist_ok=True)
        img0_0 = os.path.join(raw_dir, "step_000_t0.tif")
        img0_1 = os.path.join(raw_dir, "step_000_t1.tif")
        img1_0 = os.path.join(raw_dir, "step_001_t0.tif")
        for path in [img0_0, img0_1, img1_0]:
            arr = np.ones((100, 100), dtype=np.uint8) * 128
            Image.fromarray(arr).save(path)

        vp.ap_run_dir = self.test_dir

        # Start live run with 2 configured tiles
        vp.ap_start_live_run(['0.0', '0.1'])
        rect0_initial = QRect(vp.ap_tile_rects['0.0'])
        rect1_initial = QRect(vp.ap_tile_rects['0.1'])

        prog0 = ApproachProgress(
            state='CALIBRATING_BASELINE', step_index=0, slices_cut_total=0,
            depth_removed_um=0.0, max_depth_um=10.0, current_batch_slice=0,
            batch_slices=5, triggered_tiles=[], run_dir=self.test_dir,
            message="Baseline: evaluated tile 0.0"
        )
        rec0_part = {
            'step_index': 0,
            'depth_removed_um': 0.0,
            'tile_evaluations': {
                '0.0': {'raw_image_path': img0_0, 'shift_yx_px': [0.0, 0.0]}
            }
        }

        # Step 0: only tile 0.0 arrives
        vp.ap_update_live_step(prog0, rec0_part)
        # Grid must NOT collapse to 1 tile
        self.assertEqual(len(vp.ap_tile_rects), 2)
        self.assertEqual(vp.ap_tile_rects['0.0'], rect0_initial)
        self.assertEqual(vp.ap_tile_rects['0.1'], rect1_initial)

        # Step 0: tile 0.1 arrives
        rec0_full = {
            'step_index': 0,
            'depth_removed_um': 0.0,
            'tile_evaluations': {
                '0.1': {'raw_image_path': img0_1, 'shift_yx_px': [0.0, 0.0]}
            }
        }
        vp.ap_update_live_step(prog0, rec0_full)
        self.assertEqual(vp.ap_tile_rects['0.0'], rect0_initial)
        self.assertEqual(vp.ap_tile_rects['0.1'], rect1_initial)

        # Step 1: tile 0.0 arrives first; tile 0.1 is pending
        prog1 = ApproachProgress(
            state='EVALUATING', step_index=1, slices_cut_total=5,
            depth_removed_um=0.25, max_depth_um=10.0, current_batch_slice=0,
            batch_slices=5, triggered_tiles=[], run_dir=self.test_dir,
            message="Step 1: evaluated tile 0.0"
        )
        rec1_part = {
            'step_index': 1,
            'depth_removed_um': 0.25,
            'tile_evaluations': {
                '0.0': {'raw_image_path': img1_0, 'shift_yx_px': [1.0, 0.0], 'dissimilarity': 0.05}
            }
        }
        vp.ap_update_live_step(prog1, rec1_part)

        # Grid must remain stable and unchanged in Step 1 partial update
        self.assertEqual(len(vp.ap_tile_rects), 2)
        self.assertEqual(vp.ap_tile_rects['0.0'], rect0_initial)
        self.assertEqual(vp.ap_tile_rects['0.1'], rect1_initial)
        self.assertFalse(vp.QLabel_ApproachCanvas.pixmap().isNull())

    def test_ap_cumulative_shift_pyramid_scaling(self):
        """AC-AA-FP-019: Cumulative shift must scale by 2^pyramid_level."""
        vp, _ = build_test_viewport(self.test_dir)
        vp.ap_calibrations = {
            '0.0': {'pyramid_level': 2}  # scale_factor = 4
        }
        vp.ap_steps = [
            {
                'step_index': 0,
                'tile_evaluations': {
                    '0.0': {'shift_yx_px': [0.0, 0.0]}
                }
            },
            {
                'step_index': 1,
                'tile_evaluations': {
                    '0.0': {'shift_yx_px': [1.5, 2.0]}
                }
            },
            {
                'step_index': 2,
                'tile_evaluations': {
                    '0.0': {'shift_yx_px': [-0.5, 1.0]}
                }
            }
        ]
        # At step 1: dy = 1.5 * 4 = 6.0, dx = 2.0 * 4 = 8.0
        dy1, dx1 = vp.ap_get_cumulative_shift('0.0', 1)
        self.assertAlmostEqual(dy1, 6.0)
        self.assertAlmostEqual(dx1, 8.0)

        # At step 2: dy = (1.5 - 0.5) * 4 = 4.0, dx = (2.0 + 1.0) * 4 = 12.0
        dy2, dx2 = vp.ap_get_cumulative_shift('0.0', 2)
        self.assertAlmostEqual(dy2, 4.0)
        self.assertAlmostEqual(dx2, 12.0)

    def test_ap_draw_overlay_uses_current_step_cumulative_shift(self):
        """AC-AA-FP-019: Overlay rendering must include the current step's cumulative shift."""
        vp, _ = build_test_viewport(self.test_dir)
        raw_dir = os.path.join(self.test_dir, "raw")
        os.makedirs(raw_dir, exist_ok=True)
        img0_path = os.path.join(raw_dir, "step_000_t0.tif")
        img1_path = os.path.join(raw_dir, "step_001_t0.tif")
        Image.fromarray(np.ones((100, 100), dtype=np.uint8) * 128).save(img0_path)
        Image.fromarray(np.ones((100, 100), dtype=np.uint8) * 140).save(img1_path)

        vp.ap_run_dir = self.test_dir
        vp.ap_calibrations = {'0.0': {'pyramid_level': 0}}
        vp.ap_steps = [
            {
                'step_index': 0,
                'depth_removed_um': 0.0,
                'tile_evaluations': {
                    '0.0': {'raw_image_path': img0_path, 'shift_yx_px': [0.0, 0.0]}
                }
            },
            {
                'step_index': 1,
                'depth_removed_um': 0.05,
                'tile_evaluations': {
                    '0.0': {'raw_image_path': img1_path, 'shift_yx_px': [10.0, 5.0], 'contact_detected': True}
                }
            }
        ]
        vp.ap_max_steps = 1
        vp.ap_current_step = 1

        # Test both raw and overlay mode run without error and produce valid pixmaps
        vp.ap_raw_mode = False
        vp.ap_draw()
        self.assertFalse(vp.QLabel_ApproachCanvas.pixmap().isNull())

        vp.ap_raw_mode = True
        vp.ap_draw()
        self.assertFalse(vp.QLabel_ApproachCanvas.pixmap().isNull())


if __name__ == '__main__':
    unittest.main()
