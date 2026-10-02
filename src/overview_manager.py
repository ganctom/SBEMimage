# -*- coding: utf-8 -*-

# ==============================================================================
#   This source file is part of SBEMimage (github.com/SBEMimage)
#   (c) 2018-2020 Friedrich Miescher Institute for Biomedical Research, Basel,
#   and the SBEMimage developers.
#   This software is licensed under the terms of the MIT License.
#   See LICENSE.txt in the project root folder.
# ==============================================================================

"""This module manages the overview images (region-of-interest overviews [OV])
and the stub overview images. It can add, delete and modify overviews, and read
parameters from existing overviews.
The classes Overview and StubOverview are derived from class Grid in
grid_manager.py.
One instance of the OverviewManager class is used throughout SBEMimage as
self.ovm ('ovm' short for overview_manager).
The attributes of overviews be accessed with square brackets, for
example:
self.ovm[ov_index].dwell_time  (dwell_time of the specified overview)
self.ovm['stub'].size  (size of the stub overview grid)
"""

import os
import json
from PyQt5.QtGui import QPixmap, QPainter, QColor, QImage, QPixmapCache

import logging
from typing import Optional

import numpy as np
import utils
from grid_manager import Grid


class Overview(Grid):
    def __init__(self, coordinate_system, sem,
                 ov_active, centre_sx_sy, rotation=0, frame_size=None,
                 frame_size_selector=None, pixel_size=None, dwell_time=None,
                 dwell_time_selector=None, acq_interval=1,
                 acq_interval_offset=0, wd_stig_xy=None, vp_file_path='',
                 debris_detection_area=None):

        # Use default OV frame size selector if selector not specified
        if frame_size_selector is None:
            frame_size_selector = sem.STORE_RES_DEFAULT_INDEX_OV

        # Initialize the overview as a 1x1 grid
        super().__init__(coordinate_system, sem,
                         active=ov_active, origin_sx_sy=centre_sx_sy,
                         rotation=rotation, size=[1, 1], overlap=0, row_shift=0, shift_margin=0,
                         active_tiles=[0], frame_size=frame_size,
                         frame_size_selector=frame_size_selector,
                         pixel_size=pixel_size, dwell_time=dwell_time,
                         dwell_time_selector=dwell_time_selector,
                         display_colour=10, acq_interval=acq_interval,
                         acq_interval_offset=acq_interval_offset,
                         wd_stig_xy=wd_stig_xy)

        self.image = None
        self.vp_file_path = vp_file_path    # this will load the image if found
        self.debris_detection_area = debris_detection_area

    @property
    def centre_sx_sy(self):
        """Override centre_sx_sy from the parent class. Since overviews are 1x1
        grids, the centre is the same as the origin.
        """
        return self._origin_sx_sy

    @centre_sx_sy.setter
    def centre_sx_sy(self, sx_sy):
        self._origin_sx_sy = np.array(sx_sy)

    @property
    def centre_dx_dy(self):
        return self.cs.convert_s_to_d(self._origin_sx_sy)

    @property
    def magnification(self):
        return (self.sem.MAG_PX_SIZE_FACTOR
                / (self.frame_size[0] * self.pixel_size))

    @magnification.setter
    def magnification(self, mag):
        # Calculate and set pixel size:
        self.pixel_size = (self.sem.MAG_PX_SIZE_FACTOR
                           / (self.frame_size[0] * mag))

    @property
    def vp_file_path(self):
        return self._vp_file_path

    @vp_file_path.setter
    def vp_file_path(self, file_path):
        self._vp_file_path = file_path
        # Load OV image as QPixmap:
        if os.path.isfile(file_path):
            QPixmapCache.clear()
            self.image = QPixmap.fromImage(QImage(file_path))
        else:
            # Show blue transparent ROI when no OV image found
            blank = QPixmap(self.width_p(), self.height_p())
            blank.fill(QColor(255, 255, 255, 0))
            self.image = blank
            qp = QPainter()
            qp.begin(self.image)
            qp.setPen(QColor(0, 0, 255, 0))
            qp.setBrush(QColor(0, 0, 255, 70))
            qp.drawRect(0, 0, self.width_p(), self.height_p())
            qp.end()

    def bounding_box(self):
        centre_dx, centre_dy = self.centre_dx_dy
        # Top left corner of OV in d coordinate system:
        top_left_dx = centre_dx - self.width_d() / 2
        top_left_dy = centre_dy - self.height_d() / 2
        bottom_right_dx = top_left_dx + self.width_d()
        bottom_right_dy = top_left_dy + self.height_d()
        return (top_left_dx, top_left_dy, bottom_right_dx, bottom_right_dy)

    def update_debris_detection_area(self, grid_manager,
                                     auto_detection=True, margin=0):
        """Change the debris detection area to cover all tiles from all grids
        that fall within the overview specified by ov_number."""
        if auto_detection:
            ov_pixel_size = self.pixel_size
            ov_width_d = self.width_d()
            ov_height_d = self.height_d()
            centre_dx, centre_dy = self.centre_dx_dy
            half_w = ov_width_d / 2.0
            half_h = ov_height_d / 2.0

            theta_rad = np.radians(self.rotation)
            cos_th = np.cos(theta_rad)
            sin_th = np.sin(theta_rad)

            # The following corner coordinates in the OV coordinate frame
            # (in microns, relative to OV image top-left) define the debris area:
            u_min, v_min = None, None
            u_max, v_max = None, None

            # Check all grids for active tile overlap with OV
            for grid_index in range(grid_manager.number_grids):
                if not grid_manager[grid_index].active:
                    continue
                grid = grid_manager[grid_index]
                for tile_index in grid.active_tiles:
                    if hasattr(grid, 'tile_corners'):
                        corners = grid.tile_corners(tile_index)
                    else:
                        min_dx, max_dx, min_dy, max_dy = grid.tile_bounding_box(tile_index)
                        corners = [(min_dx, min_dy), (max_dx, min_dy),
                                   (max_dx, max_dy), (min_dx, max_dy)]

                    # Project corners into OV coordinate frame (u, v in microns):
                    tile_u = []
                    tile_v = []
                    for x, y in corners:
                        dx = x - centre_dx
                        dy = y - centre_dy
                        u = (dx * cos_th + dy * sin_th) + half_w
                        v = (-dx * sin_th + dy * cos_th) + half_h
                        tile_u.append(u)
                        tile_v.append(v)

                    tile_u_min = min(tile_u)
                    tile_u_max = max(tile_u)
                    tile_v_min = min(tile_v)
                    tile_v_max = max(tile_v)

                    # Is tile within or overlapping the OV image frame [0, ov_width_d] x [0, ov_height_d]?
                    overlap = not (tile_u_min >= ov_width_d
                                   or tile_v_min >= ov_height_d
                                   or tile_u_max <= 0
                                   or tile_v_max <= 0)
                    if overlap:
                        if u_min is None or tile_u_min < u_min:
                            u_min = tile_u_min
                        if v_min is None or tile_v_min < v_min:
                            v_min = tile_v_min
                        if u_max is None or tile_u_max > u_max:
                            u_max = tile_u_max
                        if v_max is None or tile_v_max > v_max:
                            v_max = tile_v_max

            if u_min is None:
                top_left_px, top_left_py = 0, 0
                bottom_right_px = self.width_p()
                bottom_right_py = self.height_p()
            else:
                # Now in pixel coordinates of OV image:
                top_left_px = int(u_min * 1000.0 / ov_pixel_size)
                top_left_py = int(v_min * 1000.0 / ov_pixel_size)
                bottom_right_px = int(u_max * 1000.0 / ov_pixel_size)
                bottom_right_py = int(v_max * 1000.0 / ov_pixel_size)
                # Add/subtract margin and clamp to OV image boundaries:
                top_left_px = utils.fit_in_range(
                    top_left_px - margin, 0, self.width_p())
                top_left_py = utils.fit_in_range(
                    top_left_py - margin, 0, self.height_p())
                bottom_right_px = utils.fit_in_range(
                    bottom_right_px + margin, 0, self.width_p())
                bottom_right_py = utils.fit_in_range(
                    bottom_right_py + margin, 0, self.height_p())
            # set calculated detection area:
            self.debris_detection_area = [
                top_left_px, top_left_py, bottom_right_px, bottom_right_py]
        else:
            # set full detection area:
            self.debris_detection_area = [0, 0, self.width_p(), self.height_p()]


class StubOverview(Grid):

    def __init__(self, coordinate_system, sem,
                 centre_sx_sy, grid_size, overlap, frame_size_selector,
                 pixel_size, dwell_time_selector, vp_file_path):

        # Initialize the stub overview as a grid
        super().__init__(coordinate_system, sem,
                         active=True, origin_sx_sy=[0, 0],
                         rotation=0, size=grid_size,
                         overlap=overlap, row_shift=0, shift_margin=0, active_tiles=[],
                         frame_size=None, frame_size_selector=frame_size_selector,
                         pixel_size=pixel_size, dwell_time=None,
                         dwell_time_selector=dwell_time_selector,
                         display_colour=11)

        # Set the centre coordinates, which will update the origin.
        self.centre_sx_sy = centre_sx_sy
        # QPixmaps of current stub OV (original and downsampled)
        self.pixmaps_ = {1: None, 2: None, 4: None, 8: None, 16: None}
        # QPixmaps are loaded when file path is set/changed.
        self.vp_file_path = vp_file_path

    def image(self, mag=1):
        if mag in [1, 2, 4, 8, 16]:
            return self.pixmaps_[mag]
        return None

    @property
    def vp_file_path(self):
        return self._vp_file_path

    @vp_file_path.setter
    def vp_file_path(self, file_path):
        self._vp_file_path = file_path
        # Load images as QPixmaps:
        # Full resolution  
        if os.path.isfile(file_path):
            QPixmapCache.clear()
            self.pixmaps_[1] = QPixmap.fromImage(QImage(file_path))
        else:
            self.pixmaps_[1] = None
        # Downsampled 
        for mag in [2, 4, 8, 16]:
            vp_file_path_mag = file_path[:-4] + f'_mag{mag}.png'
            if os.path.isfile(vp_file_path_mag): 
                self.pixmaps_[mag] = QPixmap.fromImage(QImage(vp_file_path_mag))
            else:
                self.pixmaps_[mag] = None

class OverviewManager:
    def __init__(self, config, sem, coordinate_system):
        self.cfg = config
        self.sem = sem
        self.cs = coordinate_system
        self.template_ov_index = 0
        self.number_ov = int(self.cfg['overviews']['number_ov'])

        # Load OV parameters from session configuration
        ov_active = json.loads(self.cfg['overviews']['ov_active'])
        ov_centre_sx_sy = json.loads(self.cfg['overviews']['ov_centre_sx_sy'])
        ov_rotation = json.loads(self.cfg['overviews']['ov_rotation'])
        ov_size = json.loads(self.cfg['overviews']['ov_size'])
        ov_size_selector = json.loads(self.cfg['overviews']['ov_size_selector'])

        ov_pixel_size = json.loads(
            self.cfg['overviews']['ov_pixel_size'])
        # self.calculate_ov_mag_from_pixel_size()
        ov_dwell_time = json.loads(self.cfg['overviews']['ov_dwell_time'])
        ov_dwell_time_selector = json.loads(
            self.cfg['overviews']['ov_dwell_time_selector'])
        ov_wd_stig_xy = json.loads(self.cfg['overviews']['ov_wd_stig_xy'])
        ov_acq_interval = json.loads(
            self.cfg['overviews']['ov_acq_interval'])
        ov_acq_interval_offset = json.loads(
            self.cfg['overviews']['ov_acq_interval_offset'])
        ov_vp_file_paths = json.loads(
            self.cfg['overviews']['ov_viewport_images'])
        debris_detection_area = json.loads(
            self.cfg['debris']['detection_area'])

        # Backward compatibility for loading older config files
        if len(ov_active) < self.number_ov:
            ov_active = [1] * self.number_ov
        if len(ov_rotation) < self.number_ov:
            ov_rotation = [0] * self.number_ov
        if len(ov_wd_stig_xy) < self.number_ov:
            ov_wd_stig_xy = [[0, 0, 0]] * self.number_ov

        # Create OV objects
        self.__overviews = []
        for i in range(self.number_ov):
            overview = Overview(self.cs, self.sem, ov_active[i] == 1,
                                ov_centre_sx_sy[i], ov_rotation[i], ov_size[i],
                                ov_size_selector[i], ov_pixel_size[i],
                                ov_dwell_time[i], ov_dwell_time_selector[i],
                                ov_acq_interval[i], ov_acq_interval_offset[i],
                                ov_wd_stig_xy[i], ov_vp_file_paths[i],
                                debris_detection_area[i])
            self.__overviews.append(overview)

        self.use_auto_debris_area = (
            self.cfg['debris']['auto_detection_area'].lower() == 'true')
        self.auto_debris_area_margin = int(
            self.cfg['debris']['auto_area_margin'])
        self.detection_area_visible = (
            self.cfg['debris']['show_detection_area'].lower() == 'true')

        # Load stub OV settings
        # The acq parameters (frame size, pixel size, dwell time) can at the
        # moment only be changed manually in the config file.

        stub_ov_centre_sx_sy = json.loads(
            self.cfg['overviews']['stub_ov_centre_sx_sy'])
        stub_ov_grid_size = json.loads(
            self.cfg['overviews']['stub_ov_grid_size'])
        stub_ov_overlap = int(self.cfg['overviews']['stub_ov_overlap'])  
        if self.cfg['overviews']['stub_ov_frame_size_selector'] == 'None':
            stub_ov_frame_size_selector = self.sem.STORE_RES_DEFAULT_INDEX_STUB_OV
        else:
            stub_ov_frame_size_selector = int(
                self.cfg['overviews']['stub_ov_frame_size_selector'])
        stub_ov_pixel_size = float(self.cfg['overviews']['stub_ov_pixel_size'])
        if self.cfg['overviews']['stub_ov_dwell_time_selector'] == 'None':
            stub_ov_dwell_time_selector = self.sem.DWELL_TIME_DEFAULT_INDEX
        else:
            stub_ov_dwell_time_selector = int(
                self.cfg['overviews']['stub_ov_dwell_time_selector'])
        stub_ov_file_path = (
            self.cfg['overviews']['stub_ov_viewport_image'])

        self.__stub_overview = StubOverview(self.cs, self.sem,
                                            stub_ov_centre_sx_sy,
                                            stub_ov_grid_size,
                                            stub_ov_overlap,
                                            stub_ov_frame_size_selector,
                                            stub_ov_pixel_size,
                                            stub_ov_dwell_time_selector,
                                            stub_ov_file_path)

    def __getitem__(self, ov_index):
        """Return the Overview object selected by index."""
        if ov_index == 'stub':
            return self.__stub_overview
        elif ov_index < self.number_ov:
            return self.__overviews[ov_index]
        else:
            return None

    def save_to_cfg(self):
        self.cfg['overviews']['number_ov'] = str(self.number_ov)
        self.cfg['overviews']['ov_active'] = str(
            [int(ov.active) for ov in self.__overviews])
        self.cfg['overviews']['ov_centre_sx_sy'] = str(
            [utils.round_xy(ov.centre_sx_sy) for ov in self.__overviews])
        self.cfg['overviews']['ov_rotation'] = str(
            [ov.rotation for ov in self.__overviews])
        self.cfg['overviews']['ov_size'] = str(
            [ov.frame_size for ov in self.__overviews])
        self.cfg['overviews']['ov_size_selector'] = str(
            [ov.frame_size_selector for ov in self.__overviews])
        self.cfg['overviews']['ov_pixel_size'] = str(
            [ov.pixel_size for ov in self.__overviews])
        self.cfg['overviews']['ov_dwell_time'] = str(
            [ov.dwell_time for ov in self.__overviews])
        self.cfg['overviews']['ov_dwell_time_selector'] = str(
            [ov.dwell_time_selector for ov in self.__overviews])
        self.cfg['overviews']['ov_wd_stig_xy'] = str(
            [ov.wd_stig_xy for ov in self.__overviews])
        self.cfg['overviews']['ov_acq_interval'] = str(
            [ov.acq_interval for ov in self.__overviews])
        self.cfg['overviews']['ov_acq_interval_offset'] = str(
            [ov.acq_interval_offset for ov in self.__overviews])
        self.cfg['overviews']['ov_viewport_images'] = json.dumps(
            [ov.vp_file_path for ov in self.__overviews])
        self.cfg['debris']['auto_detection_area'] = str(
            self.use_auto_debris_area)
        self.cfg['debris']['detection_area'] = str(
            [ov.debris_detection_area for ov in self.__overviews])
        self.cfg['debris']['auto_area_margin'] = str(
            self.auto_debris_area_margin)
        self.cfg['debris']['show_detection_area'] = str(
            self.detection_area_visible)
        # Stub OV
        self.cfg['overviews']['stub_ov_centre_sx_sy'] = str(
            utils.round_xy(self.__stub_overview.centre_sx_sy))
        self.cfg['overviews']['stub_ov_grid_size'] = json.dumps(
            self.__stub_overview.size)
        self.cfg['overviews']['stub_ov_overlap'] = str(
            self.__stub_overview.overlap)
        self.cfg['overviews']['stub_ov_frame_size_selector'] = str(
            self.__stub_overview.frame_size_selector)
        self.cfg['overviews']['stub_ov_pixel_size'] = str(
            self.__stub_overview.pixel_size)
        self.cfg['overviews']['stub_ov_dwell_time'] = str(
            self.__stub_overview.dwell_time)
        self.cfg['overviews']['stub_ov_viewport_image'] = str(
            self.__stub_overview.vp_file_path)

    def add_new_overview(self, ov_active=True, centre_sx_sy=None, rotation=0,
                         frame_size=None, frame_size_selector=None, pixel_size=None,
                         dwell_time=0.8, dwell_time_selector=4,
                         acq_interval=1, acq_interval_offset=0):
        new_ov_index = self.number_ov
        if centre_sx_sy is None:
            # Position new OV next to previous OV
            x_pos, y_pos = self.__overviews[new_ov_index - 1].centre_sx_sy
            y_pos += 50
        else:
            x_pos, y_pos = centre_sx_sy

        if frame_size is None:
            frame_size = [2048, 1536]
        if frame_size_selector is None:
            frame_size_selector = 2
        if pixel_size is None:
            pixel_size = 155.0

        new_ov = Overview(self.cs, self.sem, ov_active=ov_active,
                          centre_sx_sy=[x_pos, y_pos], rotation=rotation,
                          frame_size=frame_size,
                          frame_size_selector=frame_size_selector, pixel_size=pixel_size,
                          dwell_time_selector=dwell_time_selector, dwell_time=dwell_time,
                          acq_interval=acq_interval, acq_interval_offset=acq_interval_offset,
                          wd_stig_xy=[0, 0, 0], vp_file_path='',
                          debris_detection_area=[])
        self.__overviews.append(new_ov)
        self.number_ov += 1

    def delete_overview(self):
        """Delete the overview with the highest grid index."""
        self.number_ov -= 1
        del self.__overviews[-1]

    def draw_overview(self, x, y, w, h):
        """Draw overview rectangle using mouse"""
        # Use attributes of OV at template_ov_index for new OV
        if self.template_ov_index >= self.number_ov:
            self.template_ov_index = 0
        ov = self.__overviews[self.template_ov_index]

        # Vary magnification / pixel size to get desired frame size
        pixel_size_x = w * 1000 / ov.frame_size[0]
        pixel_size_y = h * 1000 / ov.frame_size[1]
        pixel_size = max(pixel_size_x, pixel_size_y)
        # Check if valid mag
        mag = self.sem.MAG_PX_SIZE_FACTOR / (ov.frame_size[0] * pixel_size)
        if mag < 30 or mag > 3000:
            if mag < 30:
                mag = 30
            if mag > 3000:
                mag = 3000
            pixel_size = self.sem.MAG_PX_SIZE_FACTOR / (ov.frame_size[0] * mag)

        ov_width_d = ov.frame_size[0] * pixel_size / 1000
        ov_height_d = ov.frame_size[1] * pixel_size / 1000
        sx, sy = self.cs.convert_d_to_s((x + ov_width_d / 2, y + ov_height_d / 2))

        self.add_new_overview(ov_active=ov.active, centre_sx_sy=(sx, sy), rotation=0, pixel_size=pixel_size,
                              frame_size=ov.frame_size, frame_size_selector=ov.frame_size_selector,
                              dwell_time_selector=ov.dwell_time_selector, dwell_time=ov.dwell_time,
                              acq_interval=ov.acq_interval, acq_interval_offset=ov.acq_interval_offset)

    def overview_position_for_registration(self, ov_index):
        """Provide overview location (upper left corner of overview) in nanometres.
        TODO: What is the best way to deal with overview rotations?
        """
        dx, dy = self.__overviews[ov_index].centre_dx_dy
        width_d = self.__overviews[ov_index].width_d()
        height_d = self.__overviews[ov_index].height_d()
        return int((dx - width_d/2) * 1000), int((dy - height_d/2) * 1000)

    def total_number_active_overviews(self):
        """Return the total number of active overviews."""
        sum_active_overviews = 0
        for overview in self.__overviews:
            if overview.active:
                sum_active_overviews += 1
        return sum_active_overviews

    def ov_selector_list(self):
        return ['OV %d' % r for r in range(0, self.number_ov)]

    def max_acq_interval(self):
        """Return the maximum value of the acquisition interval across
        all overviews."""
        acq_intervals = []
        for overview in self.__overviews:
            acq_intervals.append(overview.acq_interval)
        return max(acq_intervals)

    def max_acq_interval_offset(self):
        """Return the maximum value of the acquisition interval offset
        across all overviews."""
        acq_interval_offsets = []
        for overview in self.__overviews:
            acq_interval_offsets.append(overview.acq_interval_offset)
        return max(acq_interval_offsets)

    def intervallic_acq_active(self):
        """Return True if intervallic acquisition is active for at least
        one active overview, otherwise return False."""
        for overview in self.__overviews:
            if overview.acq_interval > 1 and overview.active:
                return True
        return False

    def update_all_debris_detections_areas(self, grid_manager):
        for overview in self.__overviews:
            overview.update_debris_detection_area(
                grid_manager,
                self.use_auto_debris_area,
                self.auto_debris_area_margin)

    def apply_focus_stig_from_grids(self, gm, autofocus=None) -> bool:
        """Propagate stored WD and stigmation XY from the first active tile of
        each active grid to its corresponding overview (1:1 mapping by index).

        If grid N does not exist, is inactive, has no active tiles, has uninitialized
        WD, or if AFSS sweep is in progress on its reference tile, overview N
        remains unchanged.

        Returns True if at least one overview was updated, False otherwise.
        """
        if gm is None:
            return False

        updated_any = False
        try:
            for ov_index in range(self.number_ov):
                ov = self[ov_index]
                if ov is None or not ov.active:
                    continue

                # Check if matching grid exists and is active
                if ov_index >= gm.number_grids:
                    continue
                grid = gm[ov_index]
                if grid is None or not grid.active:
                    continue

                # Get first active tile index
                first_t = gm.get_first_active_tile_index(ov_index)
                if first_t is None:
                    continue

                # Guard: AFSS sweep in progress on this reference tile
                if autofocus is not None and getattr(autofocus, 'afss_active', False):
                    tile = grid[first_t]
                    if tile is not None and getattr(tile, 'autofocus_active', False):
                        logging.warning(
                            "Focus/stig transfer skipped for OV %d: AFSS sweep in progress on grid %d tile %d",
                            ov_index, ov_index, first_t
                        )
                        continue

                # Fetch focus and stigmation from first active tile
                res = gm.get_first_active_tile_wd_stig(ov_index)
                if res is None:
                    continue

                wd, stig_xy = res
                # Atomic assignment to overview
                ov.wd_stig_xy = [wd, stig_xy[0], stig_xy[1]]
                updated_any = True
                logging.info(
                    "Transferred focus/stig from Grid %d Tile %d to OV %d: WD=%.6f m, Stig=(%.3f%%, %.3f%%)",
                    ov_index, first_t, ov_index, wd, stig_xy[0], stig_xy[1]
                )

            if updated_any:
                self.save_to_cfg()

        except Exception as e:
            logging.error("Exception occurred during focus/stig transfer to overviews: %s", str(e))
            return False

        return updated_any
