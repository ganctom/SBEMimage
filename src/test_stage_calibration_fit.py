# -*- coding: utf-8 -*-
"""Unit test for Stage Calibration Least-Squares Fit and Outlier Rejection."""

import unittest
import math
import numpy as np


def fit_stage_calibration(run_results, pixel_size):
    """Mathematical extraction logic matching StageCalibrationDlg.calculate_calibration_parameters."""
    run_params = []
    for dx_list, dy_list, sx_list, sy_list in run_results:
        dx_arr = np.array(dx_list) * pixel_size / 1000.0
        dy_arr = np.array(dy_list) * pixel_size / 1000.0

        A = np.column_stack([dx_arr, dy_arr])
        b_x = np.array(sx_list)
        b_y = np.array(sy_list)

        coef_x, residuals_x, _, _ = np.linalg.lstsq(A, b_x, rcond=None)
        coef_y, residuals_y, _, _ = np.linalg.lstsq(A, b_y, rcond=None)

        a, b = coef_x
        c, d = coef_y

        rot_y = math.atan2(-b, a)
        rot_x = math.atan2(c, d)
        rot_diff = rot_x - rot_y
        if math.cos(rot_diff) < 0:
            rot_x -= math.pi
            rot_y -= math.pi
            rot_diff = rot_x - rot_y
        scale_x = abs(math.cos(rot_diff)) * math.sqrt(a**2 + b**2)
        scale_y = abs(math.cos(rot_diff)) * math.sqrt(c**2 + d**2)
        scale_x = max(0.5, min(2.0, scale_x))
        scale_y = max(0.5, min(2.0, scale_y))

        rmse_x = np.sqrt(residuals_x[0] / len(b_x)) if len(residuals_x) > 0 else 0.0
        rmse_y = np.sqrt(residuals_y[0] / len(b_y)) if len(residuals_y) > 0 else 0.0
        rmse_tot = (rmse_x + rmse_y) / 2.0

        run_params.append({
            'scale_x': scale_x, 'scale_y': scale_y,
            'rot_x': rot_x, 'rot_y': rot_y, 'rmse': rmse_tot
        })

    rmses = [p['rmse'] for p in run_params]
    med_rmse = np.median(rmses)
    valid_params = [p for p in run_params if p['rmse'] <= max(3.0 * med_rmse, 0.5)]
    if not valid_params:
        valid_params = run_params

    final_scale_x = float(np.median([p['scale_x'] for p in valid_params]))
    final_scale_y = float(np.median([p['scale_y'] for p in valid_params]))
    final_rot_x = float(np.median([p['rot_x'] for p in valid_params]))
    final_rot_y = float(np.median([p['rot_y'] for p in valid_params]))

    return {
        'scale_x': final_scale_x,
        'scale_y': final_scale_y,
        'rot_x': final_rot_x,
        'rot_y': final_rot_y,
        'med_rmse': float(med_rmse),
        'valid_count': len(valid_params),
        'total_count': len(run_params)
    }


class TestStageCalibrationFit(unittest.TestCase):
    def test_ideal_recovery(self):
        # Target values
        true_scale_x = 1.05
        true_scale_y = 0.98
        true_rot_x = 0.035
        true_rot_y = 0.020
        pixel_size = 20.0  # nm

        rot_diff = true_rot_x - true_rot_y
        a = (math.cos(true_rot_y) / math.cos(rot_diff)) * true_scale_x
        b = (-math.sin(true_rot_y) / math.cos(rot_diff)) * true_scale_x
        c = (math.sin(true_rot_x) / math.cos(rot_diff)) * true_scale_y
        d = (math.cos(true_rot_x) / math.cos(rot_diff)) * true_scale_y

        # Forward matrix M: stage = M * d_um
        M = np.array([[a, b], [c, d]])
        M_inv = np.linalg.inv(M)

        run_results = []
        # Generate 3 good runs and 1 garbage/outlier run
        for run_idx in range(3):
            dx_list, dy_list, sx_list, sy_list = [], [], [], []
            # Generate pairs of displacements
            for _ in range(12):
                sx = float(np.random.uniform(-15.0, 15.0))
                sy = float(np.random.uniform(-15.0, 15.0))
                # Compute ideal pixel shifts
                d_um = M_inv.dot([sx, sy])
                dx_px = d_um[0] * 1000.0 / pixel_size
                dy_px = d_um[1] * 1000.0 / pixel_size

                dx_list.append(dx_px)
                dy_list.append(dy_px)
                sx_list.append(sx)
                sy_list.append(sy)
            run_results.append((dx_list, dy_list, sx_list, sy_list))

        # Add 1 outlier run with huge noise/corruption
        outlier_dx = np.random.uniform(-500, 500, 12).tolist()
        outlier_dy = np.random.uniform(-500, 500, 12).tolist()
        outlier_sx = np.random.uniform(-15.0, 15.0, 12).tolist()
        outlier_sy = np.random.uniform(-15.0, 15.0, 12).tolist()
        run_results.append((outlier_dx, outlier_dy, outlier_sx, outlier_sy))

        res = fit_stage_calibration(run_results, pixel_size)

        self.assertEqual(res['total_count'], 4)
        self.assertEqual(res['valid_count'], 3)
        self.assertAlmostEqual(res['scale_x'], true_scale_x, places=4)
        self.assertAlmostEqual(res['scale_y'], true_scale_y, places=4)
        self.assertAlmostEqual(res['rot_x'], true_rot_x, places=4)
        self.assertAlmostEqual(res['rot_y'], true_rot_y, places=4)


if __name__ == '__main__':
    unittest.main()
