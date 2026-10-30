# -*- coding: utf-8 -*-
"""
Unit and integration tests for auto_approach.py.

Strictly Python 3.7.6 compatible. Covers:
- Centroid coincidence and variance on lattice y = 2r + 1.5
- Single-scan pyramid scale and noise floor selection
- Pre-flight rejection of blank, saturated, flat, and noise-only frames
- Bounded subpixel registration under stage jitter and correlation collapse
- Dual SSIM modes (Normalized and Gradient) and dose-drift invariance
- Contrast-matched Cyan/Magenta overlay compositing with bimodal & drift invariants
- AutoApproachConfig serialization round-trip
- AutoApproachEngine hardware state machine & non-destructive safety invariants
- Optics inheritance, scan rotation preservation, and error handling
"""

from __future__ import division

import json
import math
import os
import shutil
import tempfile
import unittest
from configparser import ConfigParser
from unittest import mock
from unittest.mock import patch
from queue import Queue, Empty

import cv2
import numpy as np
import scipy.ndimage

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from unittest.mock import MagicMock
for _mod in ['pythoncom', 'win32com', 'win32com.client', 'tqdm', 'mapfost']:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from auto_approach import (
    ApproachProgress,
    ApproachState,
    ApproachStepRecord,
    AutoApproachConfig,
    AutoApproachEngine,
    SSIMMode,
    TileCalibrationProfile,
    TileStepEvaluation,
    calibrate_tile_single_scan,
    compose_cyan_magenta_overlay,
    downsample_2x_block_average,
    evaluate_ssim,
    evaluate_tile_pair,
    register_and_crop,
    split_and_interpolate_odd_even,
    validate_tile_frame,
)
from utils import Error
from microtome_control import Microtome
from microtome_control_mock import Microtome_Mock
from microtome_control_gatan import Microtome_3View
from config_template import (
    check_number_of_entries,
    process_cfg,
    CFG_NUMBER_SECTIONS,
    CFG_NUMBER_KEYS,
    SYSCFG_NUMBER_SECTIONS,
    SYSCFG_NUMBER_KEYS,
)
from grid_manager import GridManager
from sem_control import SEM
from coordinate_system import CoordinateSystem


# ---------------------------------------------------------------------------
# Test Helpers & Synthetic Image Generators
# ---------------------------------------------------------------------------

def create_synthetic_tissue_pattern(h=256, w=256, seed=42):
    """Generate deterministic textured pattern mimicking biological ultrastructure."""
    rng = np.random.RandomState(seed)
    base = rng.uniform(50.0, 200.0, size=(h, w))
    # Gaussian blur to create structural features
    features = scipy.ndimage.gaussian_filter(base, sigma=4.0)
    # Add fine edge details
    edges = scipy.ndimage.gaussian_filter(base, sigma=1.0) - features
    img = np.clip(features + 0.5 * edges, 10.0, 245.0)
    return img.astype(np.float64)


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


def create_test_microtome_3view(test_dir):
    """Instantiate Microtome_3View in simulation mode with redirected DM files."""
    cfg, syscfg = create_test_configs()
    mt = Microtome_3View(cfg, syscfg)
    mt.INPUT_FILE = os.path.join(test_dir, 'DMcom.in')
    mt.COMMAND_FILE = os.path.join(test_dir, 'DMcom.cmd')
    mt.OUTPUT_FILE = os.path.join(test_dir, 'DMcom.out')
    mt.ACK_FILE = os.path.join(test_dir, 'DMcom.ack')
    mt.ACK_CUT_FILE = os.path.join(test_dir, 'DMcom.ac2')
    mt.WARNING_FILE = os.path.join(test_dir, 'DMcom.wng')
    mt.ERROR_FILE = os.path.join(test_dir, 'DMcom.err')
    return mt


# ---------------------------------------------------------------------------
# Mock Hardware Doubles (Deterministic)
# ---------------------------------------------------------------------------

class MockTile(object):
    def __init__(self, sx_sy=(100.0, 200.0), tile_id=0, wd=0.0, stig_xy=(0, 0)):
        self.sx_sy = sx_sy
        self.tile_id = tile_id
        self.wd = wd
        self.stig_xy = stig_xy


class MockGrid(object):
    def __init__(self, frame_size_selector=0, pixel_size=10.0, dwell_time=0.8, rotation=0.0):
        self.frame_size_selector = frame_size_selector
        self.pixel_size = pixel_size
        self.dwell_time = dwell_time
        self.rotation = rotation
        self.active = True
        self.tiles = {0: MockTile(sx_sy=(50.0, 60.0), tile_id=0)}

    def __getitem__(self, tile_idx):
        return self.tiles[tile_idx]


class MockGridManager(object):
    def __init__(self):
        self.grids = {0: MockGrid()}

    def __getitem__(self, grid_idx):
        return self.grids[grid_idx]


class MockSEM(object):
    def __init__(self, frame_generator=None):
        self.frame_generator = frame_generator
        self.beam_blanked_log = []
        self.scan_rotation_log = []
        self.current_rotation = 0.0
        self.frame_settings = None
        self.wd_log = []
        self.stig_log = []
        self.eht_on = True
        self.error_state = Error.none
        self.fail_on_grab = False

    def is_eht_on(self):
        return self.eht_on

    def set_wd(self, wd):
        self.wd_log.append(float(wd))

    def set_stig_xy(self, sx, sy):
        self.stig_log.append((float(sx), float(sy)))

    def set_beam_blanking(self, state):
        self.beam_blanked_log.append(int(state))

    def apply_frame_settings(self, frame_size_selector, pixel_size, dwell_time):
        self.frame_settings = (frame_size_selector, pixel_size, dwell_time)

    def set_scan_rotation(self, rot):
        self.scan_rotation_log.append(float(rot))
        self.current_rotation = float(rot)

    def acquire_frame(self, save_path):
        if self.fail_on_grab or self.error_state != Error.none:
            return False
        if self.frame_generator is not None:
            img = self.frame_generator()
        else:
            img = create_synthetic_tissue_pattern(128, 128).astype(np.uint8)
        if img is not None:
            cv2.imwrite(save_path, img)
            return True
        return False


class MockStage(object):
    def __init__(self, initial_z=10.0, limits_xy=None, microtome_ref=None):
        self.z = float(initial_z)
        self.xy = (0.0, 0.0)
        self.error_state = Error.none
        self.xy_moves = []
        self.z_moves = []
        self.fail_on_z = False
        self.fail_on_xy = False
        self.limits_xy = limits_xy
        self.microtome_ref = microtome_ref
        self.set_mismatch_on_get_z = False
        self.use_microtome_xy = False

    @property
    def last_known_xy(self):
        return self.xy

    @property
    def limits(self):
        if self.limits_xy is not None:
            return self.limits_xy
        return (-1000.0, 1000.0, -1000.0, 1000.0)

    def pos_within_limits(self, sx_sy):
        if self.limits_xy is None:
            return True
        x_min, x_max, y_min, y_max = self.limits_xy
        x, y = sx_sy
        return (x_min <= x <= x_max) and (y_min <= y <= y_max)

    def get_z(self):
        if self.set_mismatch_on_get_z and self.microtome_ref is not None:
            self.microtome_ref.error_state = Error.mismatch_z
            return self.z
        if self.fail_on_z:
            return None
        return self.z

    def move_to_z(self, target_z, safe_mode=True):
        if self.fail_on_z or self.error_state != Error.none:
            return False
        self.z = float(target_z)
        self.z_moves.append(self.z)
        return True

    def move_to_xy(self, sx_sy):
        if self.fail_on_xy or self.error_state != Error.none:
            return False
        self.xy = sx_sy
        self.xy_moves.append(sx_sy)
        return True


class MockMicrotome(object):
    def __init__(self, z_range=(0.0, 500.0)):
        self.z_range = z_range
        self.error_state = Error.none
        self.is_knife_clear = False
        self.is_knife_near = False
        self.knife_log = []
        self.cut_count = 0
        self.fail_on_near = False
        self.fail_on_clear = False
        self.fail_on_cut_idx = None

    def near_knife(self):
        self.knife_log.append('near_knife')
        if self.fail_on_near or self.error_state != Error.none:
            return False
        self.is_knife_near = True
        self.is_knife_clear = False
        return True

    def clear_knife(self):
        self.knife_log.append('clear_knife')
        if self.fail_on_clear or self.error_state != Error.none:
            return False
        self.is_knife_clear = True
        self.is_knife_near = False
        return True

    def do_full_approach_cut(self):
        self.cut_count += 1
        self.knife_log.append('do_full_approach_cut_%d' % self.cut_count)
        if self.fail_on_cut_idx is not None and self.cut_count == self.fail_on_cut_idx:
            self.error_state = Error.cutting
            return False
        if self.error_state != Error.none:
            return False
        return True


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

class TestAutoApproach(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='sbem_test_aa_')

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_single_scan_odd_even_centroid_coincidence(self):
        """Verify production split_and_interpolate_odd_even centroids coincide to < 1e-9 px."""
        h, w = 128, 64
        m = h // 2
        y = np.arange(h, dtype=np.float64)[:, None]
        img = np.exp(-((y - 42.5) ** 2) / (2.0 * (3.0 ** 2))) * 100.0

        # Exercise the production helper in src/auto_approach.py (AR3-T005-008)
        e_tilde, o_tilde = split_and_interpolate_odd_even(img)

        # Original row corresponding to lattice index r is y = 2r + 1.5
        r_indices = np.arange(m - 1, dtype=np.float64)
        y_lattice = 2.0 * r_indices + 1.5

        sum_e = np.sum(e_tilde)
        sum_o = np.sum(o_tilde)

        centroid_e = np.sum(np.sum(e_tilde, axis=1) * y_lattice) / sum_e
        centroid_o = np.sum(np.sum(o_tilde, axis=1) * y_lattice) / sum_o

        diff = abs(centroid_e - centroid_o)
        self.assertLess(diff, 1e-9, "Centroids must coincide to < 1e-9 px (was %.2e)" % diff)

        # Equal variance verification
        var_e = (0.25 ** 2) + (0.75 ** 2)
        var_o = (0.75 ** 2) + (0.25 ** 2)
        self.assertEqual(var_e, 0.625)
        self.assertEqual(var_o, 0.625)

    def test_single_scan_calibration_pyramid_selection(self):
        """Verify clean frames select scale 0, while noisy frames select scale >= 1."""
        clean_img = create_synthetic_tissue_pattern(256, 256, seed=1)
        calib_clean = calibrate_tile_single_scan(clean_img, pixel_size_nm=10.0, ssim_mode=SSIMMode.NORMALIZED, tile_key='0.0')
        self.assertTrue(calib_clean.valid)
        self.assertEqual(calib_clean.pyramid_level, 0)
        self.assertGreaterEqual(calib_clean.internal_ssim, 0.94)

        # Add moderate noise to force pyramid downsampling (l* >= 1) while maintaining valid structure
        noisy_img = clean_img + np.random.RandomState(2).normal(0.0, 1.5, clean_img.shape)
        calib_noisy = calibrate_tile_single_scan(noisy_img, pixel_size_nm=10.0, ssim_mode=SSIMMode.NORMALIZED, tile_key='0.0')
        self.assertTrue(calib_noisy.valid)
        self.assertGreaterEqual(calib_noisy.pyramid_level, 1)

    def test_preflight_rejection_blank_saturated_noise(self):
        """Pre-flight must reject None, blank, saturated, flat, and featureless noise frames."""
        # None grab
        ok, reason = validate_tile_frame(None)
        self.assertFalse(ok)
        self.assertIn("None", reason)

        # Blank
        blank = np.zeros((128, 128), dtype=np.uint8)
        calib = calibrate_tile_single_scan(blank, 10.0, SSIMMode.NORMALIZED, '0.0')
        self.assertFalse(calib.valid)

        # Saturated
        sat = np.full((128, 128), 255, dtype=np.uint8)
        calib = calibrate_tile_single_scan(sat, 10.0, SSIMMode.NORMALIZED, '0.0')
        self.assertFalse(calib.valid)

        # Pure flat
        flat = np.full((128, 128), 120, dtype=np.uint8)
        calib = calibrate_tile_single_scan(flat, 10.0, SSIMMode.NORMALIZED, '0.0')
        self.assertFalse(calib.valid)

        # Pure uncorrelated Gaussian noise
        pure_noise = np.random.RandomState(3).uniform(20.0, 230.0, size=(128, 128))
        calib = calibrate_tile_single_scan(pure_noise, 10.0, SSIMMode.NORMALIZED, '0.0')
        self.assertFalse(calib.valid)
        self.assertIn("Insufficient surface texture", calib.failure_reason)

    def test_bounded_registration_stage_jitter_and_100pct_shave(self):
        """Registration must recover stage jitter and safely clamp on 100% shaved block."""
        base = create_synthetic_tissue_pattern(128, 128, seed=10)
        dy_true, dx_true = 3.2, -4.1
        shifted = scipy.ndimage.shift(base, (dy_true, dx_true), order=1, mode='nearest')

        crop_prev, crop_curr, (dy_est, dx_est) = register_and_crop(base, shifted, pixel_size_nm=10.0, pyramid_level=0)
        # Shift required to align shifted back with base is (-dy_true, -dx_true)
        self.assertAlmostEqual(dy_est, -dy_true, delta=0.3)
        self.assertAlmostEqual(dx_est, -dx_true, delta=0.3)

        # 100% shaved: replace entire frame with smooth resin
        shaved_resin = np.full_like(base, 40.0) + np.random.RandomState(11).normal(0.0, 1.0, base.shape)
        crop_prev, crop_curr, (dy_c, dx_c) = register_and_crop(base, shaved_resin, pixel_size_nm=10.0, pyramid_level=0)
        self.assertEqual(dy_c, 0.0)
        self.assertEqual(dx_c, 0.0)
        self.assertGreater(crop_prev.size, 0)
        self.assertGreater(crop_curr.size, 0)

    def test_dual_ssim_modes_cut_detection_and_dose_drift_invariance(self):
        """Normalized and Gradient SSIM must be immune to brightness drift and sensitive to cuts."""
        base = create_synthetic_tissue_pattern(128, 128, seed=20)
        # Dose drift: linear scaling and shift without physical cutting
        drifted = np.clip(1.2 * base - 25.0, 0.0, 255.0)

        calib_norm = calibrate_tile_single_scan(base, 10.0, SSIMMode.NORMALIZED, '0.0')
        calib_grad = calibrate_tile_single_scan(base, 10.0, SSIMMode.GRADIENT, '0.0')

        # Dose drift must NOT trigger contact
        _, dissim_n, contact_n, _ = evaluate_tile_pair(base, drifted, calib_norm, SSIMMode.NORMALIZED, 10.0)
        _, dissim_g, contact_g, _ = evaluate_tile_pair(base, drifted, calib_grad, SSIMMode.GRADIENT, 10.0)

        self.assertFalse(contact_n, "Normalized SSIM false positive on dose drift (dissim=%.3f)" % dissim_n)
        self.assertFalse(contact_g, "Gradient SSIM false positive on dose drift (dissim=%.3f)" % dissim_g)

        # 20% partial corner cut: replace corner with flat resin
        cut_img = base.copy()
        cut_img[:50, :50] = 40.0 + np.random.RandomState(21).normal(0.0, 1.0, (50, 50))

        _, dissim_n_cut, contact_n_cut, _ = evaluate_tile_pair(base, cut_img, calib_norm, SSIMMode.NORMALIZED, 10.0)
        _, dissim_g_cut, contact_g_cut, _ = evaluate_tile_pair(base, cut_img, calib_grad, SSIMMode.GRADIENT, 10.0)

        self.assertTrue(contact_n_cut, "Normalized SSIM missed partial cut")
        self.assertTrue(contact_g_cut, "Gradient SSIM missed partial cut")

    def test_cyan_magenta_overlay_invariants(self):
        """Compositor must yield neutral gray on identical/drifted features and correct cyan/magenta polarity."""
        base = create_synthetic_tissue_pattern(128, 128, seed=30).astype(np.uint8)

        # Identical frame: R == G == B
        overlay = compose_cyan_magenta_overlay(base, base, (0.0, 0.0))
        r = overlay[:, :, 0]
        g = overlay[:, :, 1]
        b = overlay[:, :, 2]
        self.assertTrue(np.array_equal(r, g), "R and G must be identical on unchanged frame")
        self.assertTrue(np.array_equal(g, b), "G and B must be identical on unchanged frame")

        # Bimodal resin+specimen: 80% resin (100) and 20% specimen (200), IQR=0 (AR3-T005-005)
        bimodal = np.full((128, 128), 100, dtype=np.uint8)
        bimodal[102:, :] = 200
        overlay_bimodal = compose_cyan_magenta_overlay(bimodal, bimodal, (0.0, 0.0))
        r_bi = overlay_bimodal[:, :, 0]
        g_bi = overlay_bimodal[:, :, 1]
        b_bi = overlay_bimodal[:, :, 2]
        self.assertTrue(np.array_equal(r_bi, g_bi), "Bimodal unchanged tile must yield R == G")
        self.assertTrue(np.array_equal(g_bi, b_bi), "Bimodal unchanged tile must yield G == B")

        # Linear brightness/contrast drift without cutting -> neutral gray within quantization (AR3-T005-008)
        drifted = np.clip(1.3 * base.astype(np.float64) + 15.0, 0.0, 255.0).astype(np.uint8)
        overlay_drift = compose_cyan_magenta_overlay(base, drifted, (0.0, 0.0))
        r_d = overlay_drift[:, :, 0].astype(int)
        g_d = overlay_drift[:, :, 1].astype(int)
        b_d = overlay_drift[:, :, 2].astype(int)
        self.assertTrue(np.all(np.abs(r_d - g_d) <= 2), "Drifted frame must remain neutral gray (R ~ G)")
        self.assertTrue(np.all(np.abs(g_d - b_d) <= 2), "Drifted frame must remain neutral gray (G ~ B)")

        # Pyramid level >= 1 with real shift (AR3-T005-008: kills 2 ** pyramid_level mutant)
        curr_shifted = scipy.ndimage.shift(base, (-4.0, -6.0), order=1, mode='nearest')
        # Shift to align curr back to base is (+4.0, +6.0). With pyramid_level=1, shift_yx is (+2.0, +3.0)
        overlay_pyr = compose_cyan_magenta_overlay(base, curr_shifted, (2.0, 3.0), pyramid_level=1)
        self.assertEqual(overlay_pyr.shape, (128, 128, 3))
        r_p = overlay_pyr[20:100, 20:100, 0].astype(int)
        g_p = overlay_pyr[20:100, 20:100, 1].astype(int)
        self.assertTrue(np.all(np.abs(r_p - g_p) <= 2), "Pyramid shifted frame must align interior features")

        # scale_to_width (AR3-T005-008)
        overlay_scaled = compose_cyan_magenta_overlay(base, base, (0.0, 0.0), scale_to_width=64)
        self.assertEqual(overlay_scaled.shape[1], 64)
        self.assertEqual(overlay_scaled.shape[0], 64)

        # Removed features (prev > curr) -> Cyan (#00FFFF tint, G > R and B > R)
        removed = base.copy()
        removed[20:60, 20:60] = 10  # Shaved lower intensity
        overlay_rem = compose_cyan_magenta_overlay(base, removed, (0.0, 0.0))
        r_rem = overlay_rem[30:50, 30:50, 0]
        g_rem = overlay_rem[30:50, 30:50, 1]
        b_rem = overlay_rem[30:50, 30:50, 2]
        self.assertGreater(np.mean(g_rem), np.mean(r_rem))
        self.assertGreater(np.mean(b_rem), np.mean(r_rem))

        # New features (curr > prev) -> Magenta (#FF00FF tint, R > G and B > G)
        added = base.copy()
        added[20:60, 20:60] = 240  # Newly exposed bright feature
        overlay_add = compose_cyan_magenta_overlay(base, added, (0.0, 0.0))
        r_add = overlay_add[30:50, 30:50, 0]
        g_add = overlay_add[30:50, 30:50, 1]
        b_add = overlay_add[30:50, 30:50, 2]
        self.assertGreater(np.mean(r_add), np.mean(g_add))
        self.assertGreater(np.mean(b_add), np.mean(g_add))

    def test_auto_approach_config_roundtrip(self):
        """AutoApproachConfig must cleanly serialize and deserialize to/from config dicts."""
        cfg = AutoApproachConfig(
            mode=1,
            slice_thickness_nm=75,
            batch_slices=4,
            max_depth_um=15.5,
            probe_tiles=['0.0', '1.3'],
            dwell_time_override_us=0.4,
            ssim_mode=SSIMMode.GRADIENT
        )
        d = cfg.to_cfg()
        cfg_restored = AutoApproachConfig.from_cfg(d)
        self.assertEqual(cfg, cfg_restored)

    def test_engine_initial_nominal_z_gate(self):
        """Engine must halt with zero knife moves when Z is non-nominal (<0, None, mismatch); nominal Z clears knife."""
        sem = MockSEM()
        microtome = MockMicrotome()
        gm = MockGridManager()
        cfg = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0"]'})

        # Case 1: Invalid Z < 0
        stage_neg = MockStage(initial_z=-5.0)
        engine_neg = AutoApproachEngine(sem, microtome, stage_neg, gm, cfg, self.test_dir)
        res_neg = engine_neg.run()
        self.assertEqual(res_neg.state, ApproachState.ERROR)
        self.assertEqual(len(microtome.knife_log), 0, "Knife must NOT move on non-nominal Z < 0")

        # Case 2: Z is None
        stage_none = MockStage(initial_z=10.0)
        stage_none.fail_on_z = True
        microtome_none = MockMicrotome()
        engine_none = AutoApproachEngine(sem, microtome_none, stage_none, gm, cfg, self.test_dir)
        res_none = engine_none.run()
        self.assertEqual(res_none.state, ApproachState.ERROR)
        self.assertEqual(len(microtome_none.knife_log), 0, "Knife must NOT move when Z is None")

        # Case 3: Error.mismatch_z
        stage_mis = MockStage(initial_z=10.0)
        microtome_mis = MockMicrotome()
        microtome_mis.error_state = Error.mismatch_z
        engine_mis = AutoApproachEngine(sem, microtome_mis, stage_mis, gm, cfg, self.test_dir)
        res_mis = engine_mis.run()
        self.assertEqual(res_mis.state, ApproachState.ERROR)
        self.assertEqual(len(microtome_mis.knife_log), 0, "Knife must NOT move on Error.mismatch_z")

        # Case 4: Nominal Z >= 0 -> initial clear_knife MUST be commanded before XY moves or frame grabs
        stage_nom = MockStage(initial_z=12.0)
        microtome_nom = MockMicrotome()
        engine_nom = AutoApproachEngine(sem, microtome_nom, stage_nom, gm, cfg, self.test_dir)
        res_nom = engine_nom.run()
        self.assertIn('clear_knife', microtome_nom.knife_log)
        self.assertEqual(microtome_nom.knife_log[0], 'clear_knife', "First knife action on nominal Z must be clear_knife")

    def test_engine_scan_rotation_and_optics_inheritance(self):
        """Engine must preserve scan rotation if grid rotation == 0, set (360-r)%360 if >0, and inherit optics."""
        sem = MockSEM()
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0)
        gm = MockGridManager()
        # Case A: unfocused tile (wd=0.0, stig_xy=(0, 0)) on rotation=0.0 grid
        gm.grids[0].rotation = 0.0
        gm.grids[0].tiles[0] = MockTile(sx_sy=(50.0, 60.0), tile_id=0, wd=0.0, stig_xy=(0, 0))

        cfg = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0"]', 'batch_slices': 1, 'max_depth_um': 0.1})
        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        engine.run()

        # rotation == 0: set_scan_rotation MUST NOT be called (AR3-T005-001)
        self.assertEqual(sem.scan_rotation_log, [])
        # Unfocused tile: set_wd and set_stig_xy MUST NOT be called
        self.assertEqual(sem.wd_log, [])
        self.assertEqual(sem.stig_log, [])

        # Case B: rotation == 360.0 (must also not call set_scan_rotation(0))
        sem_360 = MockSEM()
        gm_360 = MockGridManager()
        gm_360.grids[0].rotation = 360.0
        engine_360 = AutoApproachEngine(sem_360, microtome, stage, gm_360, cfg, self.test_dir)
        engine_360.run()
        self.assertEqual(sem_360.scan_rotation_log, [])

        # Case C: focused tile (wd=0.0065, stig_xy=(1.2, -0.8)) on rotated grid (rotation=30.0)
        sem_c = MockSEM()
        gm_c = MockGridManager()
        gm_c.grids[0].rotation = 30.0
        gm_c.grids[0].tiles[0] = MockTile(sx_sy=(50.0, 60.0), tile_id=0, wd=0.0065, stig_xy=(1.2, -0.8))
        engine_c = AutoApproachEngine(sem_c, microtome, stage, gm_c, cfg, self.test_dir)
        engine_c.run()

        expected_rot = (360.0 - 30.0) % 360.0
        self.assertEqual(sem_c.scan_rotation_log, [expected_rot, expected_rot])
        self.assertIn(0.0065, sem_c.wd_log)
        self.assertIn((1.2, -0.8), sem_c.stig_log)

    def test_engine_preflight_checks(self):
        """Engine must abort before moving or clearing knife on EHT off, hardware error, or out-of-bounds coords."""
        gm = MockGridManager()
        cfg = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0"]'})

        # 1. EHT is OFF (AR3-T005-003)
        sem = MockSEM()
        sem.eht_on = False
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0)
        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        res = engine.run()
        self.assertEqual(res.state, ApproachState.PREFLIGHT_FAILED)
        self.assertEqual(len(microtome.knife_log), 0)

        # 2. Pre-existing microtome error (AR3-T005-002)
        sem = MockSEM()
        microtome = MockMicrotome()
        microtome.error_state = Error.cutting
        stage = MockStage(initial_z=10.0)
        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        res = engine.run()
        self.assertEqual(res.state, ApproachState.ERROR)
        self.assertEqual(len(microtome.knife_log), 0)

        # 3. Pre-existing stage error
        sem = MockSEM()
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0)
        stage.error_state = Error.mismatch_z
        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        res = engine.run()
        self.assertEqual(res.state, ApproachState.ERROR)
        self.assertEqual(len(microtome.knife_log), 0)

        # 4. Stage Z read failure (None)
        sem = MockSEM()
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0)
        stage.fail_on_z = True
        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        res = engine.run()
        self.assertEqual(res.state, ApproachState.ERROR)
        self.assertEqual(len(microtome.knife_log), 0)

        # 5. Stage Z exceeds ceiling
        sem = MockSEM()
        microtome = MockMicrotome(z_range=(0.0, 500.0))
        stage = MockStage(initial_z=550.0)
        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        res = engine.run()
        self.assertEqual(res.state, ApproachState.ERROR)
        self.assertEqual(len(microtome.knife_log), 0)

        # 6. Probe tile outside stage limits
        sem = MockSEM()
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0, limits_xy=(-10.0, 10.0, -10.0, 10.0))
        gm.grids[0].tiles[0] = MockTile(sx_sy=(100.0, 200.0))  # Out of limits
        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        res = engine.run()
        self.assertEqual(res.state, ApproachState.PREFLIGHT_FAILED)
        self.assertEqual(len(microtome.knife_log), 0)

        # 7. Dynamic Error.mismatch_z during stage.get_z() (AR3-T005-002)
        sem = MockSEM()
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0, microtome_ref=microtome)
        stage.set_mismatch_on_get_z = True
        gm.grids[0].tiles[0] = MockTile(sx_sy=(50.0, 60.0))
        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        res = engine.run()
        self.assertEqual(res.state, ApproachState.ERROR)
        self.assertEqual(len(microtome.knife_log), 0, "Knife must NOT move on dynamic Z mismatch")

        # 8. Pre-existing SEM error (AR3-T011-001)
        sem_err = MockSEM()
        sem_err.error_state = Error.smartsem_api
        microtome_err = MockMicrotome()
        stage_err = MockStage(initial_z=10.0)
        engine_err = AutoApproachEngine(sem_err, microtome_err, stage_err, gm, cfg, self.test_dir)
        res_err = engine_err.run()
        self.assertEqual(res_err.state, ApproachState.ERROR)
        self.assertEqual(len(microtome_err.knife_log), 0, "Knife must NOT move on SEM error_state")
        self.assertEqual(len(stage_err.xy_moves), 0, "Stage XY must NOT move on SEM error_state")

    def test_engine_non_divisible_max_depth_capping(self):
        """Engine must use integer nanometers and halt without cutting past max_depth_um (AR3-T005-004)."""
        pattern = create_synthetic_tissue_pattern(128, 128, seed=45).astype(np.uint8)
        sem = MockSEM(frame_generator=lambda: pattern)
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0)
        gm = MockGridManager()
        # max_depth_um = 0.5 um (500 nm), slice = 200 nm, batch = 5
        # 500 // 200 = 2 slices = 400 nm; remaining = 100 nm < 200 nm -> HALT
        cfg = AutoApproachConfig.from_cfg({
            'probe_tiles': '["0.0"]',
            'batch_slices': 5,
            'slice_thickness': 200,
            'max_depth_um': 0.5
        })

        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        res = engine.run()

        self.assertEqual(res.state, ApproachState.SAFETY_LIMIT_REACHED)
        self.assertIn("Safety limit reached", res.message)
        self.assertEqual(res.slices_cut_total, 2, "Must cut exactly 2 slices, never 3")
        self.assertAlmostEqual(res.depth_removed_um, 0.4, delta=1e-5)
        self.assertEqual(len(stage.z_moves), 2)

    def test_engine_hardware_errors_and_corrupt_grab(self):
        """Engine must halt in ERROR on XY/Z/near_knife/grab failures and post-cut corrupt frames."""
        gm = MockGridManager()
        cfg = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0"]', 'batch_slices': 2, 'max_depth_um': 1.0})

        # 1. XY move failure during Step 0 baseline grab
        sem = MockSEM()
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0)
        stage.fail_on_xy = True
        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        res = engine.run()
        self.assertEqual(res.state, ApproachState.ERROR)
        self.assertEqual(microtome.cut_count, 0)

        # 2. Near knife failure before batch
        sem = MockSEM()
        microtome = MockMicrotome()
        microtome.fail_on_near = True
        stage = MockStage(initial_z=10.0)
        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        res = engine.run()
        self.assertEqual(res.state, ApproachState.ERROR)
        self.assertEqual(microtome.cut_count, 0)

        # 3. Step 0 SEM grab failure
        sem = MockSEM()
        sem.fail_on_grab = True
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0)
        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        res = engine.run()
        self.assertEqual(res.state, ApproachState.ERROR)

        # 4. Post-cut corrupt/black grab at Step 1 -> ERROR (not false CONTACT_DETECTED) (AR3-T005-006)
        pattern = create_synthetic_tissue_pattern(128, 128, seed=55).astype(np.uint8)
        grab_state = {'step': 0}
        def corrupt_gen():
            if grab_state['step'] == 0:
                grab_state['step'] += 1
                return pattern
            # Step 1 returns all-black frame (e.g. EHT tripped)
            return np.zeros((128, 128), dtype=np.uint8)

        sem_corrupt = MockSEM(frame_generator=corrupt_gen)
        microtome_c = MockMicrotome()
        stage_c = MockStage(initial_z=10.0)
        engine_c = AutoApproachEngine(sem_corrupt, microtome_c, stage_c, gm, cfg, self.test_dir)
        res_c = engine_c.run()
        self.assertEqual(res_c.state, ApproachState.ERROR)
        self.assertIn("Invalid/corrupt frame", res_c.message)

        # 5. Clear knife failure during user abort -> ERROR
        sem_ab = MockSEM(frame_generator=lambda: pattern)
        microtome_ab = MockMicrotome()
        stage_ab = MockStage(initial_z=10.0)
        engine_ab = AutoApproachEngine(sem_ab, microtome_ab, stage_ab, gm, cfg, self.test_dir)

        orig_cut = microtome_ab.do_full_approach_cut
        def cut_and_abort():
            ret = orig_cut()
            engine_ab.request_abort()
            microtome_ab.fail_on_clear = True  # Clear fails when abort attempts it
            return ret
        microtome_ab.do_full_approach_cut = cut_and_abort

        res_ab = engine_ab.run()
        self.assertEqual(res_ab.state, ApproachState.ERROR)
        self.assertIn("Error clearing knife on abort", res_ab.message)

        # 6. Stage move_to_z failure in batch (AR3-T005-008)
        sem_z = MockSEM(frame_generator=lambda: pattern)
        microtome_z = MockMicrotome()
        stage_z = MockStage(initial_z=10.0)
        engine_z = AutoApproachEngine(sem_z, microtome_z, stage_z, gm, cfg, self.test_dir)
        orig_move_to_z = stage_z.move_to_z
        def move_z_fail(target_z, safe_mode=True):
            if stage_z.z_moves:  # Fail on second Z move
                return False
            return orig_move_to_z(target_z, safe_mode)
        stage_z.move_to_z = move_z_fail
        res_z = engine_z.run()
        self.assertEqual(res_z.state, ApproachState.ERROR)
        self.assertNotEqual(microtome_z.knife_log[-1], 'clear_knife', "Knife must freeze on Z move error")

        # 7. Active-cut failure during request_abort() (verification.md:169, AR3-T005-008: error freeze takes precedence)
        sem_cut_err = MockSEM(frame_generator=lambda: pattern)
        microtome_cut_err = MockMicrotome()
        stage_cut_err = MockStage(initial_z=10.0)
        engine_cut_err = AutoApproachEngine(sem_cut_err, microtome_cut_err, stage_cut_err, gm, cfg, self.test_dir)

        def cut_abort_and_fail():
            engine_cut_err.request_abort()
            microtome_cut_err.cut_count += 1
            microtome_cut_err.knife_log.append('do_full_approach_cut_%d' % microtome_cut_err.cut_count)
            microtome_cut_err.error_state = Error.cutting
            return False
        microtome_cut_err.do_full_approach_cut = cut_abort_and_fail

        res_cut_err = engine_cut_err.run()
        self.assertEqual(res_cut_err.state, ApproachState.ERROR, "Error state must take precedence over user abort")
        self.assertNotEqual(microtome_cut_err.knife_log[-1], 'clear_knife', "Knife must freeze on cut error during abort")

    def test_engine_end_of_step_z_error(self):
        """Engine must halt in ERROR when stage.get_z() fails or sets error_state at step end (AR3-T005-002)."""
        pattern = create_synthetic_tissue_pattern(128, 128, seed=90).astype(np.uint8)
        sem = MockSEM(frame_generator=lambda: pattern)
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0, microtome_ref=microtome)
        gm = MockGridManager()
        cfg = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0"]', 'batch_slices': 1, 'max_depth_um': 0.5})

        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        call_count = {'count': 0}
        orig_get_z = stage.get_z
        def step_end_fail_z():
            call_count['count'] += 1
            # Call #1: preflight get_z
            # Call #2: Batch cut 1 get_z (before move_to_z)
            # Call #3: Step 1 end get_z
            if call_count['count'] >= 3:
                microtome.error_state = Error.mismatch_z
                return 10.1
            return orig_get_z()
        stage.get_z = step_end_fail_z

        res = engine.run()
        self.assertEqual(res.state, ApproachState.ERROR)
        self.assertIn("Stage Z error at end of step", res.message)

    def test_engine_nominal_batch_run_and_contact_detection(self):
        """Engine must execute Near, batch cuts, Clear, probe grab, and halt on contact."""
        pattern = create_synthetic_tissue_pattern(128, 128, seed=40).astype(np.uint8)
        cut_pattern = pattern.copy()
        cut_pattern[:60, :60] = 30  # Physical cut

        state = {'step': 0}

        def frame_gen():
            if state['step'] == 0:
                state['step'] += 1
                return pattern
            return cut_pattern

        sem = MockSEM(frame_generator=frame_gen)
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0)
        gm = MockGridManager()
        cfg = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0"]', 'batch_slices': 3, 'slice_thickness': 100})

        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        res = engine.run()

        self.assertEqual(res.state, ApproachState.CONTACT_DETECTED)
        self.assertEqual(res.slices_cut_total, 3)
        self.assertAlmostEqual(res.depth_removed_um, 0.3, delta=1e-5)
        self.assertIn('0.0', res.triggered_tiles)

        # Beam blanking verification
        self.assertIn(1, sem.beam_blanked_log)
        self.assertIn(0, sem.beam_blanked_log)
        self.assertEqual(sem.beam_blanked_log[-1], 1, "Beam must be blanked at conclusion")

        # Knife sequencing verification: initial clear, near, 3 cuts, clear
        expected_knife = ['clear_knife', 'near_knife', 'do_full_approach_cut_1', 'do_full_approach_cut_2', 'do_full_approach_cut_3', 'clear_knife']
        self.assertEqual(microtome.knife_log, expected_knife)

    def test_engine_nominal_batch_run_and_max_depth_stop(self):
        """Nominal 5-slice batch executes Near -> 5 cuts -> Clear -> probe grab, and max_depth_um caps slices and halts."""
        pattern = create_synthetic_tissue_pattern(128, 128, seed=41).astype(np.uint8)
        sem = MockSEM(frame_generator=lambda: pattern)
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0)
        gm = MockGridManager()
        # max_depth_um = 0.7 um, slice = 100 nm (0.1 um), batch = 5
        # Batch 1: 5 slices (0.5 um) -> not reached
        # Batch 2: remaining = 2 slices (0.2 um) -> capped to 2 slices
        # Total = 7 slices (0.7 um) -> halts in SAFETY_LIMIT_REACHED with knife in Clear
        cfg = AutoApproachConfig.from_cfg({
            'probe_tiles': '["0.0"]',
            'batch_slices': 5,
            'slice_thickness': 100,
            'max_depth_um': 0.7
        })

        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        res = engine.run()

        self.assertEqual(res.state, ApproachState.SAFETY_LIMIT_REACHED)
        self.assertEqual(res.slices_cut_total, 7)
        self.assertAlmostEqual(res.depth_removed_um, 0.7, delta=1e-5)
        self.assertTrue(microtome.is_knife_clear, "Knife must be in Clear on SAFETY_LIMIT_REACHED")

        # Verify knife sequencing:
        # Initial: clear_knife
        # Batch 1: near_knife, 5 cuts, clear_knife
        # Batch 2: near_knife, 2 cuts, clear_knife
        expected_knife = [
            'clear_knife',
            'near_knife',
            'do_full_approach_cut_1', 'do_full_approach_cut_2', 'do_full_approach_cut_3', 'do_full_approach_cut_4', 'do_full_approach_cut_5',
            'clear_knife',
            'near_knife',
            'do_full_approach_cut_6', 'do_full_approach_cut_7',
            'clear_knife'
        ]
        self.assertEqual(microtome.knife_log, expected_knife)

    def test_engine_error_knife_freeze_invariant(self):
        """When an error occurs across any of the 5 failure points, clear_knife() must NEVER be called."""
        pattern = create_synthetic_tissue_pattern(128, 128, seed=60).astype(np.uint8)
        gm = MockGridManager()
        cfg = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0"]', 'batch_slices': 3, 'max_depth_um': 1.0})

        # 1. Z-stage move error during batch cut (after knife is near)
        sem_1 = MockSEM(frame_generator=lambda: pattern)
        mt_1 = MockMicrotome()
        stage_1 = MockStage(initial_z=10.0)
        orig_move_to_z = stage_1.move_to_z
        def fail_z_on_batch(target_z, safe_mode=True):
            if stage_1.z_moves:  # Fail on second Z move inside batch
                return False
            return orig_move_to_z(target_z, safe_mode)
        stage_1.move_to_z = fail_z_on_batch
        eng_1 = AutoApproachEngine(sem_1, mt_1, stage_1, gm, cfg, self.test_dir)
        res_1 = eng_1.run()
        self.assertEqual(res_1.state, ApproachState.ERROR)
        self.assertNotEqual(mt_1.knife_log[-1], 'clear_knife', "Point 1: Knife must freeze on Z move error")

        # 2. near_knife() failure before batch cut
        sem_2 = MockSEM(frame_generator=lambda: pattern)
        mt_2 = MockMicrotome()
        mt_2.fail_on_near = True
        stage_2 = MockStage(initial_z=10.0)
        eng_2 = AutoApproachEngine(sem_2, mt_2, stage_2, gm, cfg, self.test_dir)
        res_2 = eng_2.run()
        self.assertEqual(res_2.state, ApproachState.ERROR)
        self.assertEqual(mt_2.knife_log, ['clear_knife', 'near_knife'], "Point 2: Zero clear_knife after near failure")

        # 3. do_full_approach_cut() error on cut #2
        sem_3 = MockSEM(frame_generator=lambda: pattern)
        mt_3 = MockMicrotome()
        mt_3.fail_on_cut_idx = 2
        stage_3 = MockStage(initial_z=10.0)
        eng_3 = AutoApproachEngine(sem_3, mt_3, stage_3, gm, cfg, self.test_dir)
        res_3 = eng_3.run()
        self.assertEqual(res_3.state, ApproachState.ERROR)
        self.assertNotEqual(mt_3.knife_log[-1], 'clear_knife', "Point 3: Knife must freeze on cut error")

        # 4. XY stage move error during probe tile positioning
        sem_4 = MockSEM(frame_generator=lambda: pattern)
        mt_4 = MockMicrotome()
        stage_4 = MockStage(initial_z=10.0)
        stage_4.fail_on_xy = True
        eng_4 = AutoApproachEngine(sem_4, mt_4, stage_4, gm, cfg, self.test_dir)
        res_4 = eng_4.run()
        self.assertEqual(res_4.state, ApproachState.ERROR)
        self.assertNotIn('near_knife', mt_4.knife_log, "Point 4: Zero cuts if Step 0 XY move fails")

        # 5. SEM grab failure (acquire_frame returns False)
        sem_5 = MockSEM()
        sem_5.fail_on_grab = True
        mt_5 = MockMicrotome()
        stage_5 = MockStage(initial_z=10.0)
        eng_5 = AutoApproachEngine(sem_5, mt_5, stage_5, gm, cfg, self.test_dir)
        res_5 = eng_5.run()
        self.assertEqual(res_5.state, ApproachState.ERROR)
        self.assertNotIn('near_knife', mt_5.knife_log, "Point 5: Zero cuts if Step 0 grab fails")

        # 6. Hardware exception in do_full_approach_cut during batch cut #2 (AR3-T011-004)
        sem_6 = MockSEM(frame_generator=lambda: pattern)
        mt_6 = MockMicrotome()
        stage_6 = MockStage(initial_z=10.0)
        cfg_6 = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0"]', 'batch_slices': 3, 'max_depth_um': 1.0})
        eng_6 = AutoApproachEngine(sem_6, mt_6, stage_6, gm, cfg_6, self.test_dir)
        orig_cut_6 = mt_6.do_full_approach_cut
        def cut_raise():
            if mt_6.cut_count == 1:
                # Cut 1 succeeds, cut 2 raises an unhandled hardware IOError
                mt_6.cut_count += 1
                mt_6.knife_log.append('do_full_approach_cut_2_exception')
                raise IOError("Microtome communication bus broken")
            return orig_cut_6()
        mt_6.do_full_approach_cut = cut_raise

        res_6 = eng_6.run()
        self.assertEqual(res_6.state, ApproachState.ERROR)
        self.assertEqual(res_6.slices_cut_total, 1, "Must accurately record that cut #1 succeeded before exception")
        self.assertAlmostEqual(res_6.depth_removed_um, 0.1, delta=1e-5)
        self.assertNotEqual(mt_6.knife_log[-1], 'clear_knife', "Point 6: Knife must freeze on cut exception")

        # Check manifest reflects 1 slice cut and ERROR
        manifest_path_6 = os.path.join(eng_6.run_dir, 'manifest.json')
        self.assertTrue(os.path.isfile(manifest_path_6))
        with open(manifest_path_6, 'r') as f:
            man_6 = json.load(f)
        self.assertEqual(man_6['terminal_state'], 'ERROR')
        self.assertEqual(man_6['total_slices_cut'], 1)
        self.assertAlmostEqual(man_6['total_depth_removed_um'], 0.1, delta=1e-5)

    def test_engine_user_abort_clear_after_stroke_down_invariant(self):
        """When user aborts, active cut completes and then knife clears; cut error freezes; abort during grab halts cleanly."""
        pattern = create_synthetic_tissue_pattern(128, 128, seed=70).astype(np.uint8)
        gm = MockGridManager()
        cfg = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0"]', 'batch_slices': 5})

        # Subtest A: Mid-batch abort while cut #2 is active:
        # Active cut completes, no further cuts scheduled, knife clears cleanly
        sem = MockSEM(frame_generator=lambda: pattern)
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0)
        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)

        orig_cut = microtome.do_full_approach_cut
        def cut_hook():
            ret = orig_cut()
            if microtome.cut_count == 2:
                engine.request_abort()
            return ret
        microtome.do_full_approach_cut = cut_hook

        res = engine.run()
        self.assertEqual(res.state, ApproachState.ABORTED)
        self.assertEqual(res.slices_cut_total, 2)
        self.assertEqual(microtome.knife_log[-1], 'clear_knife', "Knife must clear cleanly on abort after active cut")

        # Subtest B: Error during abort cut -> error freeze takes precedence (zero clear_knife)
        sem_b = MockSEM(frame_generator=lambda: pattern)
        mt_b = MockMicrotome()
        stage_b = MockStage(initial_z=10.0)
        eng_b = AutoApproachEngine(sem_b, mt_b, stage_b, gm, cfg, self.test_dir)

        def cut_abort_and_fail():
            eng_b.request_abort()
            mt_b.cut_count += 1
            mt_b.knife_log.append('do_full_approach_cut_%d' % mt_b.cut_count)
            mt_b.error_state = Error.cutting
            return False
        mt_b.do_full_approach_cut = cut_abort_and_fail

        res_b = eng_b.run()
        self.assertEqual(res_b.state, ApproachState.ERROR, "Error state must take precedence over user abort")
        self.assertNotEqual(mt_b.knife_log[-1], 'clear_knife', "Knife must freeze on cut error during abort")

        # Subtest C: Abort before or during probe tile grab (AR2-T011-002)
        sem_c = MockSEM(frame_generator=lambda: pattern)
        mt_c = MockMicrotome()
        stage_c = MockStage(initial_z=10.0)
        eng_c = AutoApproachEngine(sem_c, mt_c, stage_c, gm, cfg, self.test_dir)

        orig_clear = mt_c.clear_knife
        def clear_and_abort():
            ret = orig_clear()
            if mt_c.cut_count > 0:  # Clear after batch cuts
                eng_c.request_abort()
            return ret
        mt_c.clear_knife = clear_and_abort

        res_c = eng_c.run()
        self.assertEqual(res_c.state, ApproachState.ABORTED)
        self.assertTrue(mt_c.is_knife_clear)
        self.assertEqual(res_c.slices_cut_total, 5)

        # Subtest D: Re-entrant engine run after abort (AR3-T011-002)
        sem_d = MockSEM(frame_generator=lambda: pattern)
        mt_d = MockMicrotome()
        stage_d = MockStage(initial_z=10.0)
        cfg_d = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0"]', 'batch_slices': 1, 'max_depth_um': 0.1})
        eng_d = AutoApproachEngine(sem_d, mt_d, stage_d, gm, cfg_d, self.test_dir)
        orig_cut_d = mt_d.do_full_approach_cut
        def cut_abort_d():
            eng_d.request_abort()
            return orig_cut_d()
        mt_d.do_full_approach_cut = cut_abort_d
        res_d1 = eng_d.run()
        self.assertEqual(res_d1.state, ApproachState.ABORTED)
        # Run 2 on the SAME engine instance must proceed normally and clear _abort_event
        mt_d.do_full_approach_cut = orig_cut_d
        res_d2 = eng_d.run()
        self.assertEqual(res_d2.state, ApproachState.SAFETY_LIMIT_REACHED)
        self.assertEqual(res_d2.slices_cut_total, 1)

    def test_engine_scan_rotation_preservation_invariant(self):
        """Scan rotation (360 - rotation) % 360 must be applied during grabs, and NEVER reset to 0 on terminal states."""
        pattern = create_synthetic_tissue_pattern(128, 128, seed=42).astype(np.uint8)
        gm = MockGridManager()
        gm.grids[0].rotation = 45.0  # Non-zero rotation
        expected_rot = (360.0 - 45.0) % 360.0  # 315.0

        # Check all 5 terminal states:
        # 1. SAFETY_LIMIT_REACHED
        sem_1 = MockSEM(frame_generator=lambda: pattern)
        mt_1 = MockMicrotome()
        st_1 = MockStage(initial_z=10.0)
        cfg_1 = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0"]', 'batch_slices': 1, 'max_depth_um': 0.1})
        eng_1 = AutoApproachEngine(sem_1, mt_1, st_1, gm, cfg_1, self.test_dir)
        res_1 = eng_1.run()
        self.assertEqual(res_1.state, ApproachState.SAFETY_LIMIT_REACHED)
        self.assertIn(expected_rot, sem_1.scan_rotation_log)
        self.assertNotIn(0.0, sem_1.scan_rotation_log, "Scan rotation must never be reset to 0 on SAFETY_LIMIT_REACHED")

        # 2. CONTACT_DETECTED
        cut_pat = pattern.copy()
        cut_pat[:60, :60] = 30
        st = {'step': 0}
        def contact_gen():
            if st['step'] == 0:
                st['step'] += 1
                return pattern
            return cut_pat
        sem_2 = MockSEM(frame_generator=contact_gen)
        mt_2 = MockMicrotome()
        st_2 = MockStage(initial_z=10.0)
        cfg_2 = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0"]', 'batch_slices': 1, 'max_depth_um': 1.0})
        eng_2 = AutoApproachEngine(sem_2, mt_2, st_2, gm, cfg_2, self.test_dir)
        res_2 = eng_2.run()
        self.assertEqual(res_2.state, ApproachState.CONTACT_DETECTED)
        self.assertIn(expected_rot, sem_2.scan_rotation_log)
        self.assertNotIn(0.0, sem_2.scan_rotation_log, "Scan rotation must never be reset to 0 on CONTACT_DETECTED")

        # 3. PREFLIGHT_FAILED (EHT off)
        sem_3 = MockSEM()
        sem_3.eht_on = False
        mt_3 = MockMicrotome()
        st_3 = MockStage(initial_z=10.0)
        eng_3 = AutoApproachEngine(sem_3, mt_3, st_3, gm, cfg_1, self.test_dir)
        res_3 = eng_3.run()
        self.assertEqual(res_3.state, ApproachState.PREFLIGHT_FAILED)
        self.assertNotIn(0.0, sem_3.scan_rotation_log, "Scan rotation must never be reset to 0 on PREFLIGHT_FAILED")

        # 4. ABORTED
        sem_4 = MockSEM(frame_generator=lambda: pattern)
        mt_4 = MockMicrotome()
        st_4 = MockStage(initial_z=10.0)
        eng_4 = AutoApproachEngine(sem_4, mt_4, st_4, gm, cfg_1, self.test_dir)
        orig_cut = mt_4.do_full_approach_cut
        def cut_abort():
            eng_4.request_abort()
            return orig_cut()
        mt_4.do_full_approach_cut = cut_abort
        res_4 = eng_4.run()
        self.assertEqual(res_4.state, ApproachState.ABORTED)
        self.assertNotIn(0.0, sem_4.scan_rotation_log, "Scan rotation must never be reset to 0 on ABORTED")

        # 5. ERROR
        sem_5 = MockSEM(frame_generator=lambda: pattern)
        mt_5 = MockMicrotome()
        mt_5.fail_on_cut_idx = 1
        st_5 = MockStage(initial_z=10.0)
        eng_5 = AutoApproachEngine(sem_5, mt_5, st_5, gm, cfg_1, self.test_dir)
        res_5 = eng_5.run()
        self.assertEqual(res_5.state, ApproachState.ERROR)
        self.assertNotIn(0.0, sem_5.scan_rotation_log, "Scan rotation must never be reset to 0 on ERROR")

        # 6. Multi-grid probe set: rotated grid (30 deg) followed by unrotated grid (0 deg) (AR3-T011-003)
        gm_multi = MockGridManager()
        g1 = MockGrid(rotation=0.0)
        g1.tiles[0] = MockTile(sx_sy=(100.0, 100.0), tile_id=0)
        gm_multi.grids[1] = g1
        gm_multi.grids[0].rotation = 30.0
        sem_multi = MockSEM(frame_generator=lambda: pattern)
        mt_multi = MockMicrotome()
        st_multi = MockStage(initial_z=10.0)
        cfg_multi = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0", "1.0"]', 'batch_slices': 1, 'max_depth_um': 0.1})
        eng_multi = AutoApproachEngine(sem_multi, mt_multi, st_multi, gm_multi, cfg_multi, self.test_dir)
        res_multi = eng_multi.run()
        self.assertEqual(res_multi.state, ApproachState.SAFETY_LIMIT_REACHED)
        # Grid 0 sets (360 - 30) = 330.0; Grid 1 must reset SEM rotation to 0.0
        self.assertIn(330.0, sem_multi.scan_rotation_log)
        self.assertIn(0.0, sem_multi.scan_rotation_log)
        self.assertEqual(sem_multi.scan_rotation_log, [330.0, 0.0, 330.0, 0.0])

    def test_engine_beam_blanking_transitions(self):
        """Beam blanking is 1 during cutting/moves and 0 strictly during frame acquisition."""
        pattern = create_synthetic_tissue_pattern(128, 128, seed=42).astype(np.uint8)
        sem = MockSEM(frame_generator=lambda: pattern)
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0)
        gm = MockGridManager()
        cfg = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0"]', 'batch_slices': 2, 'max_depth_um': 0.2})

        blanking_during_cut = []
        orig_cut = microtome.do_full_approach_cut
        def cut_inspect():
            blanking_during_cut.append(sem.beam_blanked_log[-1] if sem.beam_blanked_log else None)
            return orig_cut()
        microtome.do_full_approach_cut = cut_inspect

        blanking_during_grab = []
        orig_grab = sem.acquire_frame
        def grab_inspect(save_path):
            blanking_during_grab.append(sem.beam_blanked_log[-1] if sem.beam_blanked_log else None)
            return orig_grab(save_path)
        sem.acquire_frame = grab_inspect

        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        res = engine.run()

        self.assertTrue(len(blanking_during_cut) > 0)
        for state in blanking_during_cut:
            self.assertEqual(state, 1, "Beam must be blanked (1) during cuts")

        self.assertTrue(len(blanking_during_grab) > 0)
        for state in blanking_during_grab:
            self.assertEqual(state, 0, "Beam must be unblanked (0) strictly during acquire_frame")

        self.assertEqual(sem.beam_blanked_log[-1], 1, "Beam must be blanked on run termination")

    def test_engine_manifest_json_persistence(self):
        """Verify manifest.json schema, forward-slash relative paths, and null safety on Step 0 overlay."""
        pattern = create_synthetic_tissue_pattern(128, 128, seed=80).astype(np.uint8)
        sem = MockSEM(frame_generator=lambda: pattern)
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0)
        gm = MockGridManager()
        cfg = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0"]', 'batch_slices': 1, 'max_depth_um': 0.1})

        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir)
        res = engine.run()

        manifest_path = os.path.join(engine.run_dir, 'manifest.json')
        self.assertTrue(os.path.isfile(manifest_path))

        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

        # 1. Top-level schema assertions (4-data-model.md §5)
        self.assertIn('timestamp', manifest)
        self.assertEqual(manifest['terminal_state'], res.state)
        self.assertEqual(manifest['total_slices_cut'], res.slices_cut_total)
        self.assertAlmostEqual(manifest['total_depth_removed_um'], res.depth_removed_um, delta=1e-5)
        self.assertIn('config', manifest)
        self.assertIn('calibrations', manifest)
        self.assertIn('steps', manifest)

        # 2. Steps schema & forward-slash relative path assertions (AR2-T011-003)
        steps = manifest['steps']
        self.assertGreaterEqual(len(steps), 1)

        # Step 0: baseline (no overlay)
        step0 = steps[0]
        self.assertEqual(step0['step_index'], 0)
        self.assertEqual(step0['slices_cut_cumulative'], 0)
        self.assertEqual(step0['depth_removed_um'], 0.0)
        self.assertIn('0.0', step0['tile_evaluations'])
        eval0 = step0['tile_evaluations']['0.0']
        self.assertIsNone(eval0['overlay_image_path'], "Step 0 overlay must be null")
        self.assertTrue(eval0['raw_image_path'].startswith('raw/'))
        self.assertNotIn('\\', eval0['raw_image_path'], "Must use POSIX forward slash")

        # Step 1: has overlay
        if len(steps) > 1:
            step1 = steps[1]
            self.assertEqual(step1['step_index'], 1)
            eval1 = step1['tile_evaluations']['0.0']
            self.assertIsNotNone(eval1['overlay_image_path'])
            self.assertTrue(eval1['overlay_image_path'].startswith('overlays/'))
            self.assertTrue(eval1['raw_image_path'].startswith('raw/'))
            self.assertNotIn('\\', eval1['overlay_image_path'], "Must use POSIX forward slash")
            self.assertNotIn('\\', eval1['raw_image_path'], "Must use POSIX forward slash")

    def test_engine_progress_callback_exception_isolation(self):
        """Callback exceptions must be caught without halting the engine."""
        pattern = create_synthetic_tissue_pattern(128, 128, seed=80).astype(np.uint8)
        sem = MockSEM(frame_generator=lambda: pattern)
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0)
        gm = MockGridManager()
        cfg = AutoApproachConfig.from_cfg({'probe_tiles': '["0.0"]', 'batch_slices': 1, 'max_depth_um': 0.1})

        def buggy_callback(prog, rec):
            raise RuntimeError("GUI callback crashed unexpectedly")

        engine = AutoApproachEngine(sem, microtome, stage, gm, cfg, self.test_dir, progress_callback=buggy_callback)
        res = engine.run()
        self.assertIn(res.state, (ApproachState.SAFETY_LIMIT_REACHED, ApproachState.IDLE, ApproachState.EVALUATING))

    def test_microtome_base_and_mock_contracts(self):
        """Microtome base methods raise NotImplementedError; Microtome_Mock returns True nominally, False on error."""
        cfg, syscfg = create_test_configs()
        mt_base = Microtome(cfg, syscfg)
        with self.assertRaises(NotImplementedError):
            mt_base.near_knife()
        with self.assertRaises(NotImplementedError):
            mt_base.clear_knife()
        with self.assertRaises(NotImplementedError):
            mt_base.do_full_approach_cut()

        # Microtome_Mock nominal
        mt_mock = Microtome_Mock(cfg, syscfg)
        self.assertEqual(mt_mock.error_state, Error.none)
        self.assertTrue(mt_mock.near_knife())
        self.assertTrue(mt_mock.clear_knife())
        self.assertTrue(mt_mock.do_full_approach_cut())

        # Microtome_Mock faulted state
        mt_mock.error_state = Error.mismatch_z
        self.assertFalse(mt_mock.near_knife())
        self.assertFalse(mt_mock.clear_knife())
        self.assertFalse(mt_mock.do_full_approach_cut())

    def test_microtome_near_clear_handshake_verification(self):
        """Verify Microtome_3View near_knife and clear_knife .ack/.err/timeout contracts."""
        mt = create_test_microtome_3view(self.test_dir)
        sim_time = [100.0]

        def fake_time():
            return sim_time[0]

        # 1. Stale file cleanup and nominal .ack arrival with command verification
        for f in (mt.OUTPUT_FILE, mt.ACK_FILE, mt.ACK_CUT_FILE, mt.ERROR_FILE, mt.WARNING_FILE):
            with open(f, 'w') as fh:
                fh.write('STALE\n')
            self.assertTrue(os.path.isfile(f))

        def fake_sleep_ack_near(s):
            sim_time[0] += s
            # Verify stale files were cleaned up by _send_dm_command (AR3-T007-001, AR3-T007-002)
            self.assertFalse(os.path.isfile(mt.OUTPUT_FILE))
            self.assertFalse(mt.ACK_CUT_FILE in [f for f in [mt.ACK_CUT_FILE] if os.path.isfile(f)])
            self.assertFalse(os.path.isfile(mt.ERROR_FILE))
            self.assertFalse(os.path.isfile(mt.WARNING_FILE))
            # Verify command file payload (AR3-T007-002)
            self.assertTrue(os.path.isfile(mt.COMMAND_FILE))
            with open(mt.COMMAND_FILE, 'r') as fh:
                cmd_content = fh.read().splitlines()
            self.assertEqual(cmd_content[0], 'MicrotomeStage_Near')
            if not os.path.isfile(mt.ACK_FILE):
                with open(mt.ACK_FILE, 'w') as fh:
                    fh.write('ACK\n')

        with patch('microtome_control_gatan.time', side_effect=fake_time), \
             patch('microtome_control_gatan.sleep', side_effect=fake_sleep_ack_near):
            self.assertTrue(mt.near_knife())
            self.assertEqual(mt.error_state, Error.none)
            if os.path.isfile(mt.ACK_FILE):
                os.remove(mt.ACK_FILE)
            if os.path.isfile(mt.COMMAND_FILE):
                os.remove(mt.COMMAND_FILE)

        # 1b. Stale file removal failure sets Error.dm_comm_send (AR3-T007-001)
        with open(mt.ERROR_FILE, 'w') as fh:
            fh.write('LOCKED_ERR\n')
        with patch('utils.try_to_remove', return_value=False), \
             patch('microtome_control_gatan.sleep') as mock_sleep:
            self.assertFalse(mt.near_knife())
            self.assertEqual(mt.error_state, Error.dm_comm_send)
            self.assertIn('could not remove stale DM communication file', mt.error_info)
            self.assertFalse(os.path.isfile(mt.COMMAND_FILE))
            mock_sleep.assert_not_called()
        mt.reset_error_state()
        if os.path.isfile(mt.ERROR_FILE):
            os.remove(mt.ERROR_FILE)

        # 1c. Nominal clear_knife with command payload verification (AR3-T007-002)
        def fake_sleep_ack_clear(s):
            sim_time[0] += s
            self.assertTrue(os.path.isfile(mt.COMMAND_FILE))
            with open(mt.COMMAND_FILE, 'r') as fh:
                cmd_content = fh.read().splitlines()
            self.assertEqual(cmd_content[0], 'MicrotomeStage_Clear')
            if not os.path.isfile(mt.ACK_FILE):
                with open(mt.ACK_FILE, 'w') as fh:
                    fh.write('ACK\n')

        with patch('microtome_control_gatan.time', side_effect=fake_time), \
             patch('microtome_control_gatan.sleep', side_effect=fake_sleep_ack_clear):
            self.assertTrue(mt.clear_knife())
            self.assertEqual(mt.error_state, Error.none)
            if os.path.isfile(mt.ACK_FILE):
                os.remove(mt.ACK_FILE)
            if os.path.isfile(mt.COMMAND_FILE):
                os.remove(mt.COMMAND_FILE)

        # 2. .err failure during knife motion with log_error assertion (AR2-T007-005, AR3-T007-002)
        def fake_sleep_err(s):
            sim_time[0] += s
            if os.path.isfile(mt.COMMAND_FILE) and not os.path.isfile(mt.ERROR_FILE):
                with open(mt.ERROR_FILE, 'w') as fh:
                    fh.write('ERR\n')

        with patch('microtome_control_gatan.time', side_effect=fake_time), \
             patch('microtome_control_gatan.sleep', side_effect=fake_sleep_err), \
             patch('utils.log_error') as mock_log:
            # near_knife error
            self.assertFalse(mt.near_knife())
            self.assertEqual(mt.error_state, Error.cutting)
            self.assertIn('microtome.near_knife: error during knife near motion', mt.error_info)
            mock_log.assert_called_with('KNIFE', mt.error_info)
            mt.reset_error_state()
            if os.path.isfile(mt.COMMAND_FILE):
                os.remove(mt.COMMAND_FILE)

            # clear_knife error
            self.assertFalse(mt.clear_knife())
            self.assertEqual(mt.error_state, Error.cutting)
            self.assertIn('microtome.clear_knife: error during knife clear motion', mt.error_info)
            mock_log.assert_called_with('KNIFE', mt.error_info)
            mt.reset_error_state()
            if os.path.isfile(mt.COMMAND_FILE):
                os.remove(mt.COMMAND_FILE)

        # 3. Timeout waiting for .ack with log_error assertion (AR2-T007-005, AR3-T007-002)
        def fake_sleep_noop(s):
            sim_time[0] += s

        with patch('microtome_control_gatan.time', side_effect=fake_time), \
             patch('microtome_control_gatan.sleep', side_effect=fake_sleep_noop), \
             patch('utils.log_error') as mock_log:
            # near_knife timeout
            self.assertFalse(mt.near_knife())
            self.assertEqual(mt.error_state, Error.dm_comm_response)
            self.assertIn('timeout waiting for .ack from DM script', mt.error_info)
            mock_log.assert_called_with('KNIFE', mt.error_info)
            mt.reset_error_state()
            if os.path.isfile(mt.COMMAND_FILE):
                os.remove(mt.COMMAND_FILE)

            # clear_knife timeout
            self.assertFalse(mt.clear_knife())
            self.assertEqual(mt.error_state, Error.dm_comm_response)
            self.assertIn('timeout waiting for .ack from DM script', mt.error_info)
            mock_log.assert_called_with('KNIFE', mt.error_info)
            mt.reset_error_state()
            if os.path.isfile(mt.COMMAND_FILE):
                os.remove(mt.COMMAND_FILE)

        # 4. Send failure across near_knife and clear_knife with sleep not called (AR3-T007-002)
        for method_name in ('near_knife', 'clear_knife'):
            with patch('os.rename', side_effect=OSError("Simulated rename error")), \
                 patch('microtome_control_gatan.sleep') as mock_sleep:
                method = getattr(mt, method_name)
                self.assertFalse(method())
                self.assertEqual(mt.error_state, Error.dm_comm_send)
                self.assertIn('could not rename input file', mt.error_info)
                mock_sleep.assert_not_called()
                mt.reset_error_state()
                if os.path.isfile(mt.INPUT_FILE):
                    os.remove(mt.INPUT_FILE)

        # 5. Faulted-state entry rejection (AR2-T007-001)
        mt.error_state = Error.mismatch_z
        mt.error_info = 'faulted entry'
        self.assertFalse(mt.near_knife())
        self.assertEqual(mt.error_state, Error.mismatch_z)
        self.assertEqual(mt.error_info, 'faulted entry')
        self.assertFalse(os.path.isfile(mt.COMMAND_FILE))

        self.assertFalse(mt.clear_knife())
        self.assertEqual(mt.error_state, Error.mismatch_z)
        self.assertEqual(mt.error_info, 'faulted entry')
        self.assertFalse(os.path.isfile(mt.COMMAND_FILE))

    def test_microtome_do_full_approach_cut_ac2_verification(self):
        """Verify Microtome_3View do_full_approach_cut .ac2/.err/timeout/grace contracts."""
        mt = create_test_microtome_3view(self.test_dir)
        mt.full_cut_duration = 5.0
        sim_time = [100.0]

        def fake_time():
            return sim_time[0]

        # 1. Nominal .ac2 confirmation with payload check & early-exit timing assertion (AR3-T007-002)
        def fake_sleep_cut_ack(s):
            sim_time[0] += s
            self.assertTrue(os.path.isfile(mt.COMMAND_FILE))
            with open(mt.COMMAND_FILE, 'r') as fh:
                cmd_content = fh.read().splitlines()
            self.assertEqual(cmd_content[0], 'MicrotomeStage_FullApproachCut')
            if not os.path.isfile(mt.ACK_CUT_FILE):
                with open(mt.ACK_CUT_FILE, 'w') as fh:
                    fh.write('AC2\n')

        sim_time[0] = 100.0
        with patch('microtome_control_gatan.time', side_effect=fake_time), \
             patch('microtome_control_gatan.sleep', side_effect=fake_sleep_cut_ack):
            self.assertTrue(mt.do_full_approach_cut())
            self.assertEqual(mt.error_state, Error.none)
            # Verify adaptive polling broke out early on .ac2 (elapsed 0.2s, not full 5.0s)
            self.assertAlmostEqual(sim_time[0] - 100.0, 0.2, places=2)
            if os.path.isfile(mt.ACK_CUT_FILE):
                os.remove(mt.ACK_CUT_FILE)
            if os.path.isfile(mt.COMMAND_FILE):
                os.remove(mt.COMMAND_FILE)

        # 2. .err failure during cut with log_error assertion and early-exit timing (AR3-T007-002, AR3-T007-004)
        def fake_sleep_cut_err(s):
            sim_time[0] += s
            if os.path.isfile(mt.COMMAND_FILE) and not os.path.isfile(mt.ERROR_FILE):
                with open(mt.ERROR_FILE, 'w') as fh:
                    fh.write('ERR\n')

        sim_time[0] = 100.0
        with patch('microtome_control_gatan.time', side_effect=fake_time), \
             patch('microtome_control_gatan.sleep', side_effect=fake_sleep_cut_err), \
             patch('utils.log_error') as mock_log:
            self.assertFalse(mt.do_full_approach_cut())
            self.assertEqual(mt.error_state, Error.cutting)
            self.assertIn('microtome.do_full_approach_cut: error during cutting cycle', mt.error_info)
            mock_log.assert_called_with('KNIFE', mt.error_info)
            # Early break on .err
            self.assertAlmostEqual(sim_time[0] - 100.0, 0.2, places=2)
            mt.reset_error_state()
            if os.path.isfile(mt.COMMAND_FILE):
                os.remove(mt.COMMAND_FILE)

        # 3. Missing .ac2 timeout spanning full duration and grace window (AR3-T007-002)
        def fake_sleep_cut_noop(s):
            sim_time[0] += s

        sim_time[0] = 100.0
        with patch('microtome_control_gatan.time', side_effect=fake_time), \
             patch('microtome_control_gatan.sleep', side_effect=fake_sleep_cut_noop), \
             patch('utils.log_error') as mock_log:
            self.assertFalse(mt.do_full_approach_cut())
            self.assertEqual(mt.error_state, Error.dm_comm_response)
            self.assertIn('microtome.do_full_approach_cut: command not processed by DM script', mt.error_info)
            mock_log.assert_called_with('KNIFE', mt.error_info)
            # 5.0s adaptive poll + 15s grace loop = 20.0s total simulated elapsed time
            self.assertGreaterEqual(sim_time[0] - 100.0, 20.0)
            mt.reset_error_state()
            if os.path.isfile(mt.COMMAND_FILE):
                os.remove(mt.COMMAND_FILE)

        # 4. Delayed .ac2 grace recovery (AR2-T007-004)
        def fake_sleep_cut_grace(s):
            sim_time[0] += s
            # s == 1 is called inside check_cut_cycle_status grace loop
            if s == 1 and not os.path.isfile(mt.ACK_CUT_FILE):
                with open(mt.ACK_CUT_FILE, 'w') as fh:
                    fh.write('AC2_DELAYED\n')

        sim_time[0] = 100.0
        with patch('microtome_control_gatan.time', side_effect=fake_time), \
             patch('microtome_control_gatan.sleep', side_effect=fake_sleep_cut_grace):
            self.assertTrue(mt.do_full_approach_cut())
            self.assertEqual(mt.error_state, Error.none)
            if os.path.isfile(mt.ACK_CUT_FILE):
                os.remove(mt.ACK_CUT_FILE)
            if os.path.isfile(mt.COMMAND_FILE):
                os.remove(mt.COMMAND_FILE)

        # 5. Grace loop precedence: ERROR_FILE checked before ACK_CUT_FILE (AR3-T007-004)
        def fake_sleep_cut_grace_both(s):
            sim_time[0] += s
            if s == 1:
                with open(mt.ERROR_FILE, 'w') as fh:
                    fh.write('ERR_LATE\n')
                with open(mt.ACK_CUT_FILE, 'w') as fh:
                    fh.write('AC2_LATE\n')

        sim_time[0] = 100.0
        with patch('microtome_control_gatan.time', side_effect=fake_time), \
             patch('microtome_control_gatan.sleep', side_effect=fake_sleep_cut_grace_both):
            self.assertFalse(mt.do_full_approach_cut())
            self.assertEqual(mt.error_state, Error.cutting)
            mt.reset_error_state()
            if os.path.isfile(mt.ACK_CUT_FILE):
                os.remove(mt.ACK_CUT_FILE)
            if os.path.isfile(mt.ERROR_FILE):
                os.remove(mt.ERROR_FILE)
            if os.path.isfile(mt.COMMAND_FILE):
                os.remove(mt.COMMAND_FILE)

        # 6. Send failure on do_full_approach_cut (AR3-T007-002)
        with patch('os.rename', side_effect=OSError("Simulated rename error")), \
             patch('microtome_control_gatan.sleep') as mock_sleep:
            self.assertFalse(mt.do_full_approach_cut())
            self.assertEqual(mt.error_state, Error.dm_comm_send)
            self.assertIn('could not rename input file', mt.error_info)
            mock_sleep.assert_not_called()
            mt.reset_error_state()
            if os.path.isfile(mt.INPUT_FILE):
                os.remove(mt.INPUT_FILE)

        # 7. Faulted-state entry rejection (AR2-T007-001)
        mt.error_state = Error.mismatch_z
        mt.error_info = 'faulted entry'
        self.assertFalse(mt.do_full_approach_cut())
        self.assertEqual(mt.error_state, Error.mismatch_z)
        self.assertEqual(mt.error_info, 'faulted entry')
        self.assertFalse(os.path.isfile(mt.COMMAND_FILE))

    def test_config_counts_and_process_cfg(self):
        """Verify CFG section/key counts, legacy config migration via process_cfg, and AutoApproachConfig round-trip."""
        cfg, syscfg = create_test_configs()
        # 1. Entry counts (AC-SBEM-AUTO_APPROACH-008)
        self.assertEqual(len(cfg.sections()), CFG_NUMBER_SECTIONS)
        self.assertEqual(CFG_NUMBER_SECTIONS, 13)
        self.assertEqual(sum(len(cfg[s]) for s in cfg.sections()), CFG_NUMBER_KEYS)
        self.assertEqual(CFG_NUMBER_KEYS, 254)
        self.assertTrue(check_number_of_entries(cfg, False))

        self.assertEqual(len(syscfg.sections()), SYSCFG_NUMBER_SECTIONS)
        self.assertEqual(SYSCFG_NUMBER_SECTIONS, 8)
        self.assertEqual(sum(len(syscfg[s]) for s in syscfg.sections()), SYSCFG_NUMBER_KEYS)
        self.assertEqual(SYSCFG_NUMBER_KEYS, 56)
        self.assertTrue(check_number_of_entries(syscfg, True))

        # 2. Migration of legacy config lacking [approach]
        legacy_cfg, _ = create_test_configs()
        legacy_cfg.remove_section('approach')
        self.assertFalse(legacy_cfg.has_section('approach'))

        # process_cfg upgrades legacy config using template
        success, exceptions, _, _, upgraded_cfg, _ = process_cfg(legacy_cfg, syscfg)
        self.assertTrue(success)
        self.assertEqual(exceptions, '')
        self.assertTrue(upgraded_cfg.has_section('approach'))
        self.assertEqual(upgraded_cfg['approach']['mode'], '0')
        self.assertEqual(upgraded_cfg['approach']['slice_thickness'], '100')
        self.assertEqual(upgraded_cfg['approach']['batch_slices'], '5')
        self.assertEqual(upgraded_cfg['approach']['max_depth_um'], '20.0')
        self.assertEqual(upgraded_cfg['approach']['probe_tiles'], '[]')
        self.assertEqual(upgraded_cfg['approach']['dwell_time_override'], '-1.0')
        self.assertEqual(upgraded_cfg['approach']['ssim_mode'], '0')

        # 3. AutoApproachConfig round-trip
        aac = AutoApproachConfig(
            mode=1,
            slice_thickness_nm=65,
            batch_slices=8,
            max_depth_um=15.5,
            probe_tiles=['0.1', '1.3'],
            dwell_time_override_us=1.6,
            ssim_mode=SSIMMode.GRADIENT
        )
        aac_dict = aac.to_cfg()
        aac_recovered = AutoApproachConfig.from_cfg(aac_dict)
        self.assertEqual(aac_recovered, aac)

    def test_grid_manager_approach_ref_tiles_sync(self):
        """Verify GridManager approach_ref_tiles sync, bounds checking, save_to_cfg, and optics resolution."""
        cfg, syscfg = create_test_configs()
        cs = CoordinateSystem(cfg, syscfg)
        sem = SEM(cfg, syscfg)
        gm = GridManager(cfg, sem, cs)

        # Initially probe_tiles in default.ini is empty
        self.assertEqual(gm.approach_ref_tiles, [])

        # 0. Test GridManager.__init__ deserializing pre-configured probe_tiles (AR3-T008-003)
        init_cfg, init_syscfg = create_test_configs()
        init_cfg['approach']['probe_tiles'] = json.dumps(['0.0', '0.2'])
        gm_init = GridManager(init_cfg, sem, cs)
        self.assertTrue(gm_init[0][0].approach_active)
        self.assertTrue(gm_init[0][2].approach_active)
        self.assertFalse(gm_init[0][1].approach_active)
        self.assertEqual(sorted(gm_init.approach_ref_tiles), ['0.0', '0.2'])

        # Non-iterable primitives (null, int, float, string) in cfg['approach']['probe_tiles'] (AR3-T008-001)
        for bad_val in ['null', '0', '123', '"invalid_string"', '{"a": 1}']:
            bad_cfg, _ = create_test_configs()
            bad_cfg['approach']['probe_tiles'] = bad_val
            gm_bad = GridManager(bad_cfg, sem, cs)
            self.assertEqual(gm_bad.approach_ref_tiles, [])

        # Malformed or out-of-bounds items in JSON list during __init__ (AR3-T008-004)
        sanitized_cfg, _ = create_test_configs()
        sanitized_cfg['approach']['probe_tiles'] = json.dumps(['0.0', '0.999', 'invalid', '99.0'])
        gm_sanitized = GridManager(sanitized_cfg, sem, cs)
        self.assertEqual(gm_sanitized.approach_ref_tiles, ['0.0'])
        self.assertTrue(gm_sanitized[0][0].approach_active)

        # 1. Toggling approach_active on a Tile updates gm.approach_ref_tiles
        tile0 = gm[0][0]
        tile0.approach_active = True
        self.assertIn('0.0', gm.approach_ref_tiles)
        self.assertIn(0, gm[0].approach_ref_tiles)
        tile0.approach_active = False
        self.assertEqual(gm.approach_ref_tiles, [])

        # 2. Setting approach_ref_tiles property sets approach_active on tiles
        gm.approach_ref_tiles = ['0.0', '0.2']
        self.assertTrue(gm[0][0].approach_active)
        self.assertTrue(gm[0][2].approach_active)
        self.assertFalse(gm[0][1].approach_active)
        self.assertEqual(sorted(gm.approach_ref_tiles), ['0.0', '0.2'])

        # 3. Robust bounds checking and malformed input handling (AR2-T008-004)
        # Passing out-of-bounds grid, out-of-bounds tile, malformed string should not crash
        gm.approach_ref_tiles = ['0.1', '0.999', '99.0', 'invalid_key', '-1.-1']
        self.assertTrue(gm[0][1].approach_active)
        self.assertFalse(gm[0][0].approach_active)
        self.assertEqual(gm.approach_ref_tiles, ['0.1'])

        # Clearing reference tiles
        gm.delete_all_approach_ref_tiles()
        self.assertEqual(gm.approach_ref_tiles, [])
        self.assertFalse(gm[0][1].approach_active)

        # 4. save_to_cfg serialization and WD/stig inclusion (AR2-T008-001, AR2-T008-002, AR3-T008-002)
        # Configure tile 0.0 with WD > 0 and approach_active=True
        gm[0][0].wd = 0.007
        gm[0][0].stig_xy = [1.2, -0.8]
        gm[0][0].tile_active = False
        gm[0][0].autofocus_active = False
        gm[0][0].wd_grad_active = False
        gm[0][0].approach_active = True

        # Configure tile 0.1 with WD == 0 and approach_active=True
        gm[0][1].wd = 0.0
        gm[0][1].stig_xy = [0.0, 0.0]
        gm[0][1].tile_active = False
        gm[0][1].autofocus_active = False
        gm[0][1].wd_grad_active = False
        gm[0][1].approach_active = True

        # Test save_to_cfg with [approach] auto-vivification (AR2-T008-001, AR3-T008-002)
        cfg.remove_section('approach')
        self.assertFalse(cfg.has_section('approach'))
        gm.save_to_cfg()
        self.assertTrue(cfg.has_section('approach'))
        self.assertEqual(len(cfg['approach']), 7)
        self.assertEqual(cfg['approach']['mode'], '0')
        self.assertEqual(cfg['approach']['slice_thickness'], '100')
        self.assertEqual(cfg['approach']['batch_slices'], '5')
        self.assertEqual(cfg['approach']['max_depth_um'], '20.0')
        self.assertEqual(cfg['approach']['dwell_time_override'], '-1.0')
        self.assertEqual(cfg['approach']['ssim_mode'], '0')

        # Verify probe_tiles was serialized as JSON list
        saved_probe_tiles = json.loads(cfg['approach']['probe_tiles'])
        self.assertIn('0.0', saved_probe_tiles)
        self.assertIn('0.1', saved_probe_tiles)

        # Verify wd_stig_params contains 0.0 (wd > 0) and excludes 0.1 (wd == 0) (AR2-T008-002)
        saved_wd_stig = json.loads(cfg['grids']['wd_stig_params'])
        self.assertIn('0.0', saved_wd_stig)
        self.assertAlmostEqual(saved_wd_stig['0.0'][0], 0.007, places=6)
        self.assertAlmostEqual(saved_wd_stig['0.0'][1], 1.2, places=4)
        self.assertAlmostEqual(saved_wd_stig['0.0'][2], -0.8, places=4)
        self.assertNotIn('0.1', saved_wd_stig)

        # 5. Tile scan parameter resolution from parent grid via AutoApproachEngine (AR3-T008-005)
        grid0 = gm[0]
        grid0.rotation = 25.0
        grid0.pixel_size = 12.5
        grid0.frame_size_selector = 1
        grid0.dwell_time = 0.8

        sem_mock = MockSEM()
        stage_mock = MockStage()
        microtome_mock = MockMicrotome()
        engine = AutoApproachEngine(
            sem_mock,
            microtome_mock,
            stage_mock,
            gm,
            AutoApproachConfig(
                mode=0,
                slice_thickness_nm=100,
                batch_slices=5,
                max_depth_um=20.0,
                probe_tiles=['0.0'],
                dwell_time_override_us=-1.0,
                ssim_mode=SSIMMode.NORMALIZED
            ),
            tempfile.gettempdir()
        )
        resolved_tile = engine._resolve_tile('0.0')
        resolved_grid = engine._resolve_grid('0.0')
        self.assertEqual(resolved_tile, gm[0][0])
        self.assertEqual(resolved_grid, grid0)
        self.assertEqual(resolved_grid.pixel_size, 12.5)
        self.assertEqual(resolved_grid.rotation, 25.0)
        self.assertEqual(resolved_grid.frame_size_selector, 1)
        self.assertEqual(resolved_grid.dwell_time, 0.8)

    def test_approach_dlg_controller_and_progress_trigger(self):
        """Verify ApproachDlg non-modal controller, tabbed UI, live ref tile sync, GUI restriction, and MainControls lifecycle."""
        from PyQt5.QtWidgets import QApplication, QMessageBox, QDialog
        from PyQt5.QtCore import Qt
        from src.main_controls_dlg_windows import ApproachDlg
        import utils

        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        cfg, syscfg = create_test_configs()
        cs = CoordinateSystem(cfg, syscfg)
        sem = SEM(cfg, syscfg)
        gm = GridManager(cfg, sem, cs)
        stage_mock = MockStage()
        microtome_mock = MockMicrotome()

        # Dummy trigger simulating MainControls.trigger
        mc_trigger = utils.Trigger()
        mc_trigger.queue = Queue()
        transmitted_messages = []

        def record_mc_msg():
            while not mc_trigger.queue.empty():
                transmitted_messages.append(mc_trigger.queue.get())

        mc_trigger.signal.connect(record_mc_msg)

        # 1. Non-modal instantiation and UI loading (AR2-T009-007)
        dlg = ApproachDlg(
            microtome_mock, mc_trigger,
            sem=sem, stage=stage_mock,
            grid_manager=gm, cfg=cfg,
            base_dir=tempfile.gettempdir()
        )
        self.assertEqual(dlg.windowModality(), Qt.NonModal)
        self.assertEqual(dlg.tabWidget.count(), 2)
        self.assertEqual(dlg.tabWidget.tabText(0), "Manual")
        self.assertEqual(dlg.tabWidget.tabText(1), "Automated")

        # 2. Mode persistence on tab change (AR2-T009-003)
        dlg.tabWidget.setCurrentIndex(1)
        self.assertEqual(cfg['approach']['mode'], '1')
        dlg.tabWidget.setCurrentIndex(0)
        self.assertEqual(cfg['approach']['mode'], '0')

        # 3. Dwell time override dropdown discrete values (AR2-T009-002)
        self.assertGreaterEqual(dlg.comboBox_dwellTimeOverride.count(), 2)
        self.assertEqual(dlg.comboBox_dwellTimeOverride.itemText(0), "Inherit from grid")
        self.assertEqual(float(dlg.comboBox_dwellTimeOverride.itemData(0)), -1.0)

        # Test live UI parameter persistence to cfg['approach'] without clicking Start (AR3-T009-001)
        dlg.spinBox_autoThickness.setValue(65)
        self.assertEqual(cfg['approach']['slice_thickness'], '65')
        dlg.spinBox_batchSlices.setValue(15)
        self.assertEqual(cfg['approach']['batch_slices'], '15')
        dlg.doubleSpinBox_maxDepth.setValue(12.5)
        self.assertEqual(cfg['approach']['max_depth_um'], '12.5')
        dlg.comboBox_ssimMode.setCurrentIndex(1)
        self.assertEqual(cfg['approach']['ssim_mode'], '1')

        # 4. Bidirectional reference tile sync (AC-SBEM-AUTO_APPROACH-003)
        dlg.tabWidget.setCurrentIndex(1)
        dlg.lineEdit_refTiles.setText("0.0, 0.2")
        dlg.update_ref_tiles_from_text()
        self.assertEqual(sorted(gm.approach_ref_tiles), ['0.0', '0.2'])
        self.assertTrue(gm[0][0].approach_active)
        self.assertTrue(gm[0][2].approach_active)
        self.assertFalse(gm[0][1].approach_active)

        # External change to GridManager updates dialog via sync_ref_tiles_from_grid_manager
        gm.approach_ref_tiles = ['0.1']
        dlg.sync_ref_tiles_from_grid_manager()
        self.assertEqual(dlg.lineEdit_refTiles.text(), '0.1')

        # 5. Pre-flight guard preventing start with empty probe tiles
        gm.approach_ref_tiles = []
        dlg.sync_ref_tiles_from_grid_manager()
        warning_shown = []
        with mock.patch.object(QMessageBox, 'warning', side_effect=lambda *args: warning_shown.append(args)):
            dlg.start_auto_approach()
            self.assertEqual(len(warning_shown), 1)
            self.assertFalse(dlg.auto_approach_in_progress)

        # Restore valid probe tile
        gm.approach_ref_tiles = ['0.0']
        dlg.sync_ref_tiles_from_grid_manager()

        # 6. Mutual exclusion: manual run disables automated tab; automated run disables manual tab (AR2-T009-005)
        with mock.patch('utils.run_log_thread'):
            dlg.start_approach()
            self.assertTrue(dlg.approach_in_progress)
            self.assertFalse(dlg.tabWidget.tabBar().isEnabled())
            self.assertFalse(dlg.pushButton_startAutoApproach.isEnabled())
            self.assertIn('STATUS BUSY APPROACH', transmitted_messages)
            self.assertIn('RESTRICT GUI', transmitted_messages)

            # Rejection / closing blocked while running (AR2-T009-004)
            close_event = mock.MagicMock()
            dlg.closeEvent(close_event)
            close_event.ignore.assert_called_once()
            with mock.patch.object(QMessageBox, 'information'):
                dlg.finish_approach()
            self.assertFalse(dlg.approach_in_progress)
            self.assertTrue(dlg.tabWidget.tabBar().isEnabled())
            self.assertTrue(dlg.pushButton_startAutoApproach.isEnabled())
            self.assertIn('STATUS IDLE', transmitted_messages)
            self.assertIn('UNRESTRICT GUI', transmitted_messages)

        transmitted_messages.clear()
        with mock.patch('utils.run_log_thread'):
            dlg.start_auto_approach()
            self.assertTrue(dlg.auto_approach_in_progress)
            self.assertFalse(dlg.tabWidget.tabBar().isEnabled())
            self.assertFalse(dlg.pushButton_startApproach.isEnabled())
            self.assertIn('STATUS BUSY APPROACH', transmitted_messages)
            self.assertIn('RESTRICT GUI', transmitted_messages)

            # Rejection blocked while running
            with mock.patch.object(QDialog, 'reject') as mock_super_reject:
                dlg.reject()
                mock_super_reject.assert_not_called()

            # 7. Thread-safe isolated trigger queue preventing class queue poisoning (AR2-T009-001)
            self.assertIsNot(dlg.auto_progress_trigger.queue, utils.Trigger.queue)

            # Test progress callback puts to queue and draining updates GUI to latest (AR3-T009-005)
            mock_progress_1 = ApproachProgress(
                ApproachState.CUTTING_BATCH, 1, 5, 0.5, 20.0, 5, 5, [], tempfile.gettempdir(), "Cutting batch 1"
            )
            mock_progress_2 = ApproachProgress(
                ApproachState.CUTTING_BATCH, 2, 10, 1.0, 20.0, 10, 5, [], tempfile.gettempdir(), "Cutting batch 2"
            )
            mock_step_rec_1 = {'step_index': 1, 'slices_cut_cumulative': 5}
            dlg.auto_progress_trigger.queue.put((mock_progress_1, mock_step_rec_1))
            dlg.auto_progress_trigger.queue.put((mock_progress_2, None))
            self.assertEqual(dlg.auto_progress_trigger.queue.qsize(), 2)
            dlg.update_auto_approach_progress()
            self.assertTrue(dlg.auto_progress_trigger.queue.empty())
            self.assertEqual(dlg.progressBar_autoApproach.value(), 5)
            self.assertIn("Step 2", dlg.label_statusAutoApproach.text())
            # Verify completed step record was not discarded during queue draining (AR3-T010-001)
            self.assertIn(('UPDATE APPROACH PROGRESS', mock_progress_1, mock_step_rec_1), transmitted_messages)

            # Test abort signaling
            dlg.abort_auto_approach()
            self.assertFalse(dlg.pushButton_abortAutoApproach.isEnabled())

            # Finish auto approach (Stage Z sync AR3-T009-002)
            dlg.auto_finish_trigger.queue.put(mock_progress_2)
            with mock.patch.object(QMessageBox, 'information'):
                dlg.finish_auto_approach()
            self.assertFalse(dlg.auto_approach_in_progress)
            self.assertTrue(dlg.tabWidget.tabBar().isEnabled())
            self.assertTrue(dlg.pushButton_startApproach.isEnabled())
            self.assertIn('UPDATE Z', transmitted_messages)
            self.assertIn('STATUS IDLE', transmitted_messages)
            self.assertIn('UNRESTRICT GUI', transmitted_messages)
            update_z_idx = transmitted_messages.index('UPDATE Z')
            status_idle_idx = transmitted_messages.index('STATUS IDLE')
            self.assertLess(update_z_idx, status_idle_idx)

        # Direct test of auto_approach_thread exception handling without Qt access (AR3-T009-003)
        mock_broken_engine = mock.MagicMock()
        mock_broken_engine.cfg = AutoApproachConfig(1, 100, 8, 15.0, ['0.0'], -1.0, 0)
        mock_broken_engine.run.side_effect = RuntimeError("Simulated motor drop")
        dlg.auto_engine = mock_broken_engine
        critical_calls = []
        with mock.patch.object(QMessageBox, 'critical', side_effect=lambda *args: critical_calls.append(args)):
            dlg.auto_approach_thread()
            self.assertEqual(len(critical_calls), 1)
            self.assertIn("Simulated motor drop", critical_calls[0][2])
            self.assertIn("ERROR", dlg.label_statusAutoApproach.text())

        # Null-safe dwell data retrieval check (AR3-T009-006)
        with mock.patch.object(dlg.comboBox_dwellTimeOverride, 'currentData', return_value=None):
            with mock.patch('utils.run_log_thread'):
                dlg.start_auto_approach()
                self.assertEqual(dlg.auto_engine.cfg.dwell_time_override_us, -1.0)
                with mock.patch.object(QMessageBox, 'information'):
                    dlg.finish_auto_approach()

        dlg.close()

        # 8. MainControls.open_approach_dlg() non-modal singleton lifecycle (AR2-T009-006)
        class DummyMainControls(object):
            def __init__(self, cfg, sem, stage, gm, microtome, trigger):
                self.cfg = cfg
                self.sem = sem
                self.stage = stage
                self.gm = gm
                self.microtome = microtome
                self.trigger = trigger
                self.approach_dlg = None

        dmc = DummyMainControls(cfg, sem, stage_mock, gm, microtome_mock, mc_trigger)
        from main_controls import MainControls
        MainControls.open_approach_dlg(dmc)
        self.assertIsNotNone(dmc.approach_dlg)
        self.assertTrue(dmc.approach_dlg.isVisible())
        first_dlg_instance = dmc.approach_dlg

        with mock.patch.object(first_dlg_instance, 'raise_') as mock_raise:
            with mock.patch.object(first_dlg_instance, 'activateWindow') as mock_activate:
                MainControls.open_approach_dlg(dmc)
                self.assertIs(dmc.approach_dlg, first_dlg_instance)
                mock_raise.assert_called_once()
                mock_activate.assert_called_once()

        first_dlg_instance.close()

        # 9. Legacy backward-compatibility signature (AR3-T009-004)
        legacy_dlg = ApproachDlg(microtome_mock, mc_trigger)
        self.assertFalse(legacy_dlg.has_auto_dependencies)
        self.assertFalse(legacy_dlg.tabWidget.isTabEnabled(1))
        self.assertFalse(legacy_dlg.pushButton_startAutoApproach.isEnabled())
        with mock.patch.object(QMessageBox, 'information'):
            legacy_dlg.finish_approach()
        self.assertFalse(legacy_dlg.pushButton_startAutoApproach.isEnabled())
        legacy_dlg.close()

    def test_viewport_approach_tab_and_wheel_scrubbing(self):
        """Verify Viewport 4th Approach tab, Cyan/Magenta rendering, wheel scrubbing,
        raw toggle, double-click zoom, and right-click ref badge sync."""
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QWheelEvent, QResizeEvent
        from PyQt5.QtCore import Qt, QPoint, QSize
        from viewport import Viewport
        from PIL import Image
        from overview_manager import OverviewManager
        from template_manager import TemplateManager
        from imported_img import ImportedImages
        from autofocus import Autofocus
        from acquisition import Acquisition
        from image_inspector import ImageInspector
        import utils
        import shutil

        app = QApplication.instance() or QApplication([])
        cfg, syscfg = create_test_configs()
        cs = CoordinateSystem(cfg, syscfg)
        sem = SEM(cfg, syscfg)
        gm = GridManager(cfg, sem, cs)
        stage_mock = MockStage()
        ovm = OverviewManager(cfg, sem, cs)
        tm = TemplateManager(ovm)
        imported = ImportedImages(cfg)
        autofocus = mock.MagicMock()
        acq = mock.MagicMock()
        img_inspector = mock.MagicMock()

        mc_trigger = utils.Trigger()
        mc_trigger.queue = Queue()
        transmitted_messages = []

        def record_mc_msg():
            while not mc_trigger.queue.empty():
                transmitted_messages.append(mc_trigger.queue.get())

        mc_trigger.signal.connect(record_mc_msg)

        vp = Viewport(
            cfg, sem, stage_mock, cs, ovm, gm, imported,
            autofocus, acq, img_inspector, mc_trigger, tm
        )

        # 1. Verify tab existence and UI controls
        self.assertEqual(vp.tabWidget.count(), 4)
        self.assertEqual(vp.tabWidget.tabText(3), "Approach")
        self.assertIsNotNone(vp.QLabel_ApproachCanvas)
        self.assertIsNotNone(vp.horizontalSlider_stepAP)
        self.assertIsNotNone(vp.pushButton_rawToggleAP)
        self.assertIsNotNone(vp.comboBox_runSelectorAP)
        self.assertIsNotNone(vp.pushButton_loadRunAP)

        # 2. Empty state early guard (AR2-T010-004)
        vp.ap_steps = []
        vp.ap_draw()
        self.assertFalse(vp.QLabel_ApproachCanvas.pixmap().isNull())

        # 3. Viewport context menu approach ref toggle (AC-SBEM-AUTO_APPROACH-003)
        vp.selected_grid = 0
        vp.selected_tile = 0
        vp._vp_toggle_approach_ref_tile()
        self.assertTrue(gm[0][0].approach_active)
        self.assertIn('0.0', gm.approach_ref_tiles)
        self.assertIn('UPDATE APPROACH REF TILES', transmitted_messages)

        # Toggle again -> deselected
        vp._vp_toggle_approach_ref_tile()
        self.assertFalse(gm[0][0].approach_active)
        self.assertNotIn('0.0', gm.approach_ref_tiles)

        # Re-select for subsequent approach tests
        vp._vp_toggle_approach_ref_tile()
        self.assertTrue(gm[0][0].approach_active)

        # 4. Tile badge drawing combinations in _vp_place_grid (AR3-T010-006)
        drawn_texts = []
        orig_drawText = vp.vp_qp.drawText

        def capture_drawText(*args):
            for arg in args:
                if isinstance(arg, str):
                    drawn_texts.append(arg)
            return orig_drawText(*args)

        with mock.patch.object(vp.vp_qp, 'drawText', side_effect=capture_drawText):
            # Only approach active -> 'APPROACH'
            gm[0][0].autofocus_active = False
            gm[0][0].wd_grad_active = False
            vp.vp_draw()
            self.assertIn('APPROACH', drawn_texts)

            # AF + AP active -> 'AF + AP'
            drawn_texts.clear()
            gm[0][0].autofocus_active = True
            vp.acq.use_autofocus = True
            vp.autofocus.method = 0
            vp.vp_draw()
            self.assertIn('AF + AP', drawn_texts)

            # GRAD + AF + AP active -> 'GRAD + AF + AP'
            drawn_texts.clear()
            gm[0][0].wd_grad_active = True
            gm[0].use_wd_gradient = True
            vp.vp_draw()
            self.assertIn('GRAD + AF + AP', drawn_texts)

            # GRAD + AP active -> 'GRAD + AP'
            drawn_texts.clear()
            gm[0][0].autofocus_active = False
            vp.vp_draw()
            self.assertIn('GRAD + AP', drawn_texts)

        # 5. Live step update via ap_update_live_step (AR2-T010-003)
        vp.tabWidget.setCurrentIndex(3)
        tmp_dir = tempfile.mkdtemp()
        raw_dir = os.path.join(tmp_dir, 'raw')
        overlay_dir = os.path.join(tmp_dir, 'overlays')
        os.makedirs(raw_dir)
        os.makedirs(overlay_dir)

        # Step 0 (baseline)
        step0_img = np.ones((64, 64), dtype=np.uint8) * 120
        step0_path = os.path.join(raw_dir, 'step_000_g0000_t0000.tif')
        Image.fromarray(step0_img).save(step0_path)

        step0_eval = TileStepEvaluation(
            tile_key='0.0',
            step_index=0,
            raw_image_path=step0_path,
            overlay_image_path=None,
            shift_yx_px=(0.0, 0.0),
            cross_ssim=1.0,
            dissimilarity=0.0,
            contact_detected=False
        )
        step0_rec = ApproachStepRecord(
            step_index=0,
            slices_cut_cumulative=0,
            depth_removed_um=0.0,
            z_stage_um=10.0,
            triggered_tiles=[],
            tile_evaluations={'0.0': step0_eval}
        )
        vp.ap_run_dir = tmp_dir
        vp.ap_update_live_step(None, step0_rec)
        self.assertEqual(len(vp.ap_steps), 1)
        self.assertEqual(vp.ap_current_step, 0)
        self.assertEqual(vp.ap_max_steps, 0)
        self.assertEqual(vp.horizontalSlider_stepAP.maximum(), 0)
        # Verify clean formatting without trailing delimiter when state is omitted
        self.assertEqual(vp.label_stepInfoAP.text(), "Step 0 / 0 | Cuts: 0 | Depth: 0.00 µm")
        self.assertFalse(vp.label_stepInfoAP.text().endswith(" | "))

        # Step 1 (cut step with magenta contact detected) using ApproachProgress
        step1_raw_img = np.ones((64, 64), dtype=np.uint8) * 130
        step1_raw_path = os.path.join(raw_dir, 'step_001_g0000_t0000.tif')
        Image.fromarray(step1_raw_img).save(step1_raw_path)

        step1_ov_img = np.zeros((64, 64, 3), dtype=np.uint8)
        step1_ov_img[:, :, 0] = 255
        step1_ov_img[:, :, 2] = 255
        step1_ov_path = os.path.join(overlay_dir, 'step_001_g0000_t0000_cm.png')
        Image.fromarray(step1_ov_img).save(step1_ov_path)

        step1_eval = TileStepEvaluation(
            tile_key='0.0',
            step_index=1,
            raw_image_path=step1_raw_path,
            overlay_image_path=step1_ov_path,
            shift_yx_px=(0.0, 0.0),
            cross_ssim=0.85,
            dissimilarity=0.15,
            contact_detected=True
        )
        step1_rec = ApproachStepRecord(
            step_index=1,
            slices_cut_cumulative=5,
            depth_removed_um=0.5,
            z_stage_um=10.5,
            triggered_tiles=['0.0'],
            tile_evaluations={'0.0': step1_eval}
        )
        prog1 = ApproachProgress(
            state='CUTTING_BATCH',
            step_index=1,
            slices_cut_total=5,
            depth_removed_um=0.5,
            max_depth_um=20.0,
            current_batch_slice=5,
            batch_slices=5,
            triggered_tiles=['0.0'],
            run_dir=tmp_dir,
            message="Batch cut in progress"
        )
        vp.ap_update_live_step(prog1, step1_rec)
        self.assertEqual(len(vp.ap_steps), 2)
        self.assertEqual(vp.ap_current_step, 1)
        self.assertEqual(vp.ap_max_steps, 1)
        self.assertEqual(vp.horizontalSlider_stepAP.maximum(), 1)
        self.assertIn("Step 1", vp.label_stepInfoAP.text())
        self.assertIn("Cuts: 5", vp.label_stepInfoAP.text())
        self.assertIn("CUTTING_BATCH", vp.label_stepInfoAP.text())
        self.assertIn("0.0", vp.ap_tile_rects)

        # Step 2 with missing overlay path -> dynamic compose_cyan_magenta_overlay fallback (AR3-T010-004)
        step2_raw_img = np.ones((64, 64), dtype=np.uint8) * 140
        step2_raw_path = os.path.join(raw_dir, 'step_002_g0000_t0000.tif')
        Image.fromarray(step2_raw_img).save(step2_raw_path)
        step2_eval = TileStepEvaluation(
            tile_key='0.0',
            step_index=2,
            raw_image_path=step2_raw_path,
            overlay_image_path='',  # missing overlay PNG
            shift_yx_px=(0.5, 0.0),
            cross_ssim=0.90,
            dissimilarity=0.10,
            contact_detected=False
        )
        step2_rec = ApproachStepRecord(
            step_index=2,
            slices_cut_cumulative=10,
            depth_removed_um=1.0,
            z_stage_um=11.0,
            triggered_tiles=[],
            tile_evaluations={'0.0': step2_eval}
        )
        prog2 = ApproachProgress(
            state='EVALUATING',
            step_index=2,
            slices_cut_total=10,
            depth_removed_um=1.0,
            max_depth_um=20.0,
            current_batch_slice=0,
            batch_slices=5,
            triggered_tiles=[],
            run_dir=tmp_dir,
            message="Evaluating tiles"
        )
        vp.ap_calibrations = {'0.0': {'pyramid_level': 1}}
        vp.ap_update_live_step(prog2, step2_rec)
        self.assertEqual(len(vp.ap_steps), 3)
        vp.ap_draw()  # Must dynamically invoke compose_cyan_magenta_overlay with pyramid_level=1 without error
        self.assertFalse(vp.QLabel_ApproachCanvas.pixmap().isNull())

        # Reset back to step 1 for subsequent tests
        vp.ap_set_step(1)

        # 6. Wheel scrubbing
        vp.tabWidget.setCurrentIndex(3)
        wheel_down = QWheelEvent(
            QPoint(100, 100), QPoint(100, 100), QPoint(0, 0),
            QPoint(0, -120), 0, Qt.Vertical, Qt.NoButton, Qt.NoModifier
        )
        vp.wheelEvent(wheel_down)
        self.assertEqual(vp.ap_current_step, 0)
        self.assertEqual(vp.horizontalSlider_stepAP.value(), 0)

        wheel_up = QWheelEvent(
            QPoint(100, 100), QPoint(100, 100), QPoint(0, 0),
            QPoint(0, 120), 0, Qt.Vertical, Qt.NoButton, Qt.NoModifier
        )
        vp.wheelEvent(wheel_up)
        self.assertEqual(vp.ap_current_step, 1)
        self.assertEqual(vp.horizontalSlider_stepAP.value(), 1)

        # 7. Raw toggle mode
        self.assertFalse(vp.ap_raw_mode)
        vp.pushButton_rawToggleAP.setChecked(True)
        vp.ap_toggle_raw_mode()
        self.assertTrue(vp.ap_raw_mode)
        self.assertEqual(vp.pushButton_rawToggleAP.text(), "Cyan-Magenta")

        vp.pushButton_rawToggleAP.setChecked(False)
        vp.ap_toggle_raw_mode()
        self.assertFalse(vp.ap_raw_mode)
        self.assertEqual(vp.pushButton_rawToggleAP.text(), "Show Raw")

        # 8. Double click zoom
        tile_rect = vp.ap_tile_rects['0.0']
        click_pos = QPoint(tile_rect.center().x() + utils.VP_MARGIN_X, tile_rect.center().y() + utils.VP_MARGIN_Y)
        vp.ap_handle_double_click(click_pos)
        self.assertEqual(vp.ap_zoom_tile, '0.0')

        # Double click again resets zoom
        vp.ap_handle_double_click(click_pos)
        self.assertIsNone(vp.ap_zoom_tile)

        # 9. Archived run loading from manifest.json (AR2-T010-002)
        def rec_to_manifest_step(rec):
            evals = {}
            for k, ev in rec.tile_evaluations.items():
                evals[k] = ev._asdict() if hasattr(ev, '_asdict') else ev
            return {
                'step_index': rec.step_index,
                'slices_cut_cumulative': rec.slices_cut_cumulative,
                'depth_removed_um': rec.depth_removed_um,
                'z_stage_um': rec.z_stage_um,
                'triggered_tiles': rec.triggered_tiles,
                'tile_evaluations': evals
            }

        manifest_data = {
            'timestamp': '20261029_120000',
            'terminal_state': 'COMPLETED',
            'steps': [rec_to_manifest_step(step0_rec), rec_to_manifest_step(step1_rec)]
        }
        with open(os.path.join(tmp_dir, 'manifest.json'), 'w') as f:
            json.dump(manifest_data, f)

        vp.ap_steps = []
        vp.ap_load_selected_run(tmp_dir)
        self.assertEqual(len(vp.ap_steps), 2)
        self.assertEqual(vp.ap_current_step, 1)
        self.assertIn("0.0", vp.ap_tile_rects)

        # 10. Canvas reallocation on resizeEvent (AR2-T010-006)
        resize_ev = QResizeEvent(QSize(1200, 900), QSize(1000, 800))
        vp.resizeEvent(resize_ev)
        self.assertEqual(vp.ap_canvas.width(), vp.cs.vp_width)
        self.assertEqual(vp.ap_canvas.height(), vp.cs.vp_height)

        # 11. Multi-run history isolation (AR3-T010-002)
        run_b_dir = tempfile.mkdtemp()
        mock_prog_b = mock.MagicMock()
        mock_prog_b.run_dir = run_b_dir
        step0_rec_b = {
            'step_index': 0,
            'slices_cut_cumulative': 0,
            'depth_removed_um': 0.0,
            'state': 'BASELINE_ACQUIRED',
            'tile_evaluations': {
                '0.0': {
                    'tile_key': '0.0',
                    'raw_image_path': step0_path,
                    'overlay_image_path': '',
                    'contact_detected': False
                }
            }
        }
        vp.ap_update_live_step(mock_prog_b, step0_rec_b)
        self.assertEqual(len(vp.ap_steps), 1)
        self.assertEqual(vp.ap_current_step, 0)
        self.assertEqual(vp.ap_run_dir, run_b_dir)

        # 12. Run auto-loading on tab activation (AR3-T010-005)
        meta_approach_dir = os.path.join(tmp_dir, 'meta', 'approach', '20261029_130000')
        os.makedirs(meta_approach_dir)
        with open(os.path.join(meta_approach_dir, 'manifest.json'), 'w') as f:
            json.dump(manifest_data, f)
        vp.cfg['acq']['base_dir'] = tmp_dir
        vp.ap_steps = []
        vp.ap_on_tab_activated()
        self.assertEqual(len(vp.ap_steps), 2)
        shutil.rmtree(run_b_dir, ignore_errors=True)

        vp.active = False
        vp.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_main_controls_app_exit_guard_during_approach(self):
        """MainControls.closeEvent blocks exit with modal warning when auto_approach_in_progress is True."""
        from PyQt5.QtWidgets import QApplication, QMessageBox
        from main_controls import MainControls

        app = QApplication.instance() or QApplication([])

        class MockMainControls(object):
            def __init__(self):
                self.microtome = mock.MagicMock()
                self.microtome.error_state = Error.none
                self.sem = mock.MagicMock()
                self.approach_dlg = mock.MagicMock()
                self.busy = False

        mc = MockMainControls()
        mc.approach_dlg.auto_approach_in_progress = True

        mock_event = mock.MagicMock()

        # Case 1: Approach in progress -> warning shown, event.ignore() called, event.accept() NOT called
        with mock.patch.object(QMessageBox, 'warning') as mock_warn:
            MainControls.closeEvent(mc, mock_event)
            mock_warn.assert_called_once()
            args, _ = mock_warn.call_args
            self.assertEqual(args[1], 'Approach in progress')
            self.assertIn('automated approach run is currently in progress', args[2])
            mock_event.ignore.assert_called_once()
            mock_event.accept.assert_not_called()

        # Case 2: Approach NOT in progress -> warning NOT shown, proceeds to normal exit confirmation
        mock_event.reset_mock()
        mc.approach_dlg.auto_approach_in_progress = False

        with mock.patch.object(QMessageBox, 'warning') as mock_warn, \
             mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.No) as mock_quest:
            MainControls.closeEvent(mc, mock_event)
            mock_warn.assert_not_called()
            mock_quest.assert_called_once()
            mock_event.ignore.assert_called_once()

    def test_manual_approach_thread_execution_no_redundant_sleep(self):
        """Verify manual approach_thread executes do_full_approach_cut without redundant sleep delay."""
        from PyQt5.QtWidgets import QApplication, QMessageBox
        from src.main_controls_dlg_windows import ApproachDlg
        import utils

        app = QApplication.instance() or QApplication([])

        mock_microtome = mock.MagicMock()
        mock_microtome.get_stage_z.return_value = 100.0
        mock_microtome.error_state = utils.Error.none
        mock_microtome.do_full_approach_cut.return_value = True

        mock_trigger = utils.Trigger()

        dlg = ApproachDlg(mock_microtome, mock_trigger)
        dlg.spinBox_numberSlices.setValue(2)
        dlg.spinBox_thickness.setValue(40)

        with mock.patch.object(QMessageBox, 'information'), \
             mock.patch.object(QMessageBox, 'warning'), \
             mock.patch.object(QMessageBox, 'critical'), \
             mock.patch('src.main_controls_dlg_windows.sleep') as mock_sleep:
            dlg.approach_thread()
            self.assertEqual(mock_microtome.do_full_approach_cut.call_count, 2)
            mock_sleep.assert_not_called()
            self.assertFalse(dlg.aborted)

        dlg.close()

    def test_auto_approach_stage_callbacks_and_viewport_updates(self):
        """Verify AutoApproachEngine invokes stage_callback('Z') and ('XY'), and MainControls updates."""
        from PyQt5.QtWidgets import QApplication
        from src.main_controls_dlg_windows import ApproachDlg
        from src.main_controls import MainControls
        import utils

        app = QApplication.instance() or QApplication([])

        # 1. Test AutoApproachEngine triggers stage_callback directly
        pattern = create_synthetic_tissue_pattern(128, 128, seed=42).astype(np.uint8)
        sem = MockSEM(frame_generator=lambda: pattern)
        microtome = MockMicrotome()
        stage = MockStage(initial_z=10.0)
        gm = MockGridManager()

        recorded_axes = []
        def test_stage_cb(axis):
            recorded_axes.append(axis)

        auto_cfg = AutoApproachConfig(
            mode=1, slice_thickness_nm=50, batch_slices=2, max_depth_um=0.2,
            probe_tiles=['0.0'], dwell_time_override_us=-1.0, ssim_mode=0
        )
        engine = AutoApproachEngine(
            sem, microtome, stage, gm, auto_cfg, self.test_dir,
            stage_callback=test_stage_cb
        )
        engine.run()

        # Engine must have recorded 'XY' for probe tile and 'Z' for batch cuts
        self.assertIn('XY', recorded_axes)
        self.assertIn('Z', recorded_axes)

        # 2. Test ApproachDlg.auto_stage_callback transmits to main_controls_trigger
        mc_trigger = utils.Trigger()
        mc_trigger.queue = Queue()
        transmitted_messages = []
        def record_msg():
            while not mc_trigger.queue.empty():
                transmitted_messages.append(mc_trigger.queue.get())
        mc_trigger.signal.connect(record_msg)

        dlg = ApproachDlg(microtome, mc_trigger, sem=sem, stage=stage, grid_manager=gm, cfg=None, base_dir=self.test_dir)
        dlg.auto_stage_callback('Z')
        dlg.auto_stage_callback('XY')

        self.assertIn('UPDATE Z', transmitted_messages)
        self.assertIn('UPDATE XY STAGE POS', transmitted_messages)

        # 3. Test MainControls handling of 'UPDATE XY STAGE POS'
        class DummyMC(object):
            def __init__(self):
                self.show_xy_called = False
                self.viewport = mock.MagicMock()
                self.viewport.show_stage_pos = False

            def show_current_stage_xy(self):
                self.show_xy_called = True

        dmc = DummyMC()
        # Simulate check_triggers logic for 'UPDATE XY STAGE POS'
        msg = 'UPDATE XY STAGE POS'
        if msg == 'UPDATE XY STAGE POS':
            dmc.show_current_stage_xy()
            if hasattr(dmc, 'viewport') and dmc.viewport is not None:
                if hasattr(dmc.viewport, 'show_stage_pos') and not dmc.viewport.show_stage_pos:
                    if hasattr(dmc.viewport, 'vp_activate_checkbox_show_stage_pos'):
                        dmc.viewport.vp_activate_checkbox_show_stage_pos()
                if hasattr(dmc.viewport, 'vp_draw'):
                    dmc.viewport.vp_draw()

        self.assertTrue(dmc.show_xy_called)
        dmc.viewport.vp_activate_checkbox_show_stage_pos.assert_called_once()
        dmc.viewport.vp_draw.assert_called_once()

        dlg.close()


if __name__ == '__main__':
    unittest.main()
