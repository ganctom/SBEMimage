# -*- coding: utf-8 -*-

# ==============================================================================
#   This source file is part of SBEMimage (github.com/SBEMimage)
#   (c) 2018-2020 Friedrich Miescher Institute for Biomedical Research, Basel,
#   and the SBEMimage developers.
#   This software is licensed under the terms of the MIT License.
#   See LICENSE.txt in the project root folder.
# ==============================================================================

"""This modules provides various constants."""

from enum import Enum
import re

# VERSION contains the current version/release date information for the
# master branch (for example, '2020.07 R2020-07-28'). For the current version
# in the dev (development) branch, it must contain the tag 'dev'.
# Following https://www.python.org/dev/peps/pep-0440/#public-version-identifiers
VERSION = '2022.03 dev'

# Default and minimum size of the Viewport canvas.
VP_WIDTH = 1000
VP_HEIGHT = 800

# XY margins between display area and the top-left corner of the Viewport
# window. These margins must be subtracted from the coordinates provided
# when the user clicks onto the window.
VP_MARGIN_X = 20
VP_MARGIN_Y = 40

# Difference in pixels between the Viewport window width/height and the
# Viewport canvas width/height.
VP_WINDOW_DIFF_X = 50
VP_WINDOW_DIFF_Y = 150


# Scaling parameters to convert between the scale factors and the position
# of the zoom sliders in the Viewport (VP) and the Slice-by-Slice viewer
# (SV). Settings for tiles and for OVs are stored separately because
# tiles and OVs usually differ in pixel size by an order of magnitude.


def fov_to_slider_scaling(fov, max_scale=99):
    scale_min, scale_max = 1000 / fov[1], 1000 / fov[0]
    slider_factor = scale_min
    slider_power = (scale_max / scale_min) ** (1 / max_scale)
    return slider_factor, slider_power


VP_FOV_RANGE_MICROTOME_STAGE = (40, 5000)
VP_FOV_RANGE_SEM_STAGE = (50, 200000)
SV_FOV_RANGE_OV = (50, 1000)
SV_FOV_RANGE_TILE = (4, 200)

VP_SCALING_MICROTOME_STAGE = fov_to_slider_scaling(VP_FOV_RANGE_MICROTOME_STAGE)
VP_SCALING_SEM_STAGE = fov_to_slider_scaling(VP_FOV_RANGE_SEM_STAGE)
SV_SCALING_OV = fov_to_slider_scaling(SV_FOV_RANGE_OV)
SV_SCALING_TILE = fov_to_slider_scaling(SV_FOV_RANGE_TILE)

# Number of digits used to format image file names.
OV_DIGITS = 3  # up to 999 overview images
GRID_DIGITS = 4  # up to 9999 grids
TILE_DIGITS = 4  # up to 9999 tiles per grid
SLICE_DIGITS = 5  # up to 99999 slices per stack

PRESSURE_FROM_SEM = {"mbar": 1000, "Pa": 100000, "Torr": 750.061682704}
PRESSURE_TO_SEM = {"mbar": 0.001, "Pa": 0.00001, "Torr": 0.00133322368421}

# Regular expressions for checking user input of tiles and overviews
RE_TILE_LIST = re.compile('^((0|[1-9][0-9]*)[.](0|[1-9][0-9]*))'
                          '([ ]*,[ ]*(0|[1-9][0-9]*)[.](0|[1-9][0-9]*))*$')
RE_OV_LIST = re.compile('^([0-9]+)([ ]*,[ ]*[0-9]+)*$')

# Image format / extensions
DEFAULT_IMAGE_FORMAT = '.ome.tif'
STUBOV_IMAGE_FORMAT = DEFAULT_IMAGE_FORMAT
OV_IMAGE_FORMAT = DEFAULT_IMAGE_FORMAT
GRIDTILE_IMAGE_FORMAT = DEFAULT_IMAGE_FORMAT
FRAME_IMAGE_FORMAT = DEFAULT_IMAGE_FORMAT
TEMP_IMAGE_FORMAT = '.tif'
SCREENSHOT_FORMAT = '.png'

LOG_FILENAME = 'log/SBEMimage.log'
# Custom date/time / format to get '.' instead of ',' as millisecond separator
LOG_FORMAT = '%(asctime)s.%(msecs)03d %(levelname)s %(category)s: %(message)s'
LOG_FORMAT_SCREEN = '%(asctime)s | %(category)-5s : %(message)s'
LOG_FORMAT_DATETIME = '%Y-%m-%d %H:%M:%S'
LOG_MAX_FILESIZE = 10000000
LOG_MAX_FILECOUNT = 20

# Constants for Automated Focus Stigmator Series
FOCUS = 'focus'
STIG_X = 'stig_x'
STIG_Y = 'stig_y'
AVG = 'Average'
SPECIFIC = 'tile_specific'
FOCUS_SPC_STIG_AVG = 'focus_specific_stig_average'

AFSS_LABELS = {FOCUS: 'Focus', STIG_X: 'Stigmator X', STIG_Y: 'Stigmator Y'}

# Available image sizes at ZEISS Gemini SEM and Merlin SEM
tile_sizes = {'mask_8k': (8192, 6144),
              'mask_6k': (6144, 4608),
              'mask_4k': (4096, 3072),
              'mask_3k': (3072, 2304),
              'mask_2k': (2048, 1536),
              'mask_1k': (1024, 768),
              'mask_0k': (512, 384)}


# List of selectable colours for grids (0-9), overviews (10)
# acquisition indicator (11):
COLOUR_SELECTOR = [
    [255, 0, 0],  # 0  red (default colour for grid 0)
    [0, 255, 0],  # 1  green
    [255, 255, 0],  # 2  yellow
    [0, 255, 255],  # 3  cyan
    [128, 0, 0],  # 4  dark red
    [0, 128, 0],  # 5  dark green
    [255, 165, 0],  # 6  orange
    [255, 0, 255],  # 7  pink
    [173, 216, 230],  # 8  grey
    [184, 134, 11],  # 9  brown
    [0, 0, 255],  # 10 blue (used only for OVs)
    [50, 50, 50],  # 11 dark grey for stub OV border
    [128, 0, 128, 80],  # 12 transparent violet (to indicate live acq)
    [255, 195, 0]  # 13 bright orange (active user flag, measuring tool)
]
