# pyOCD debugger
# Copyright (c) 2019-2020 Arm Limited
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ..family.target_lpc5500 import LPC5500Family
from ...core.memory_map import (FlashRegion, RamRegion, RomRegion, MemoryMap)
from ...debug.svd.loader import SVDFile

FLASH_ALGO = {
    'load_address' : 0x20000000,

    # Flash algorithm as a hex string
    'instructions': [
    0xE00ABE00, 0x062D780D, 0x24084068, 0xD3000040, 0x1E644058, 0x1C49D1FA, 0x2A001E52, 0x4770D1F2,
    0xf240b580, 0xf2c00004, 0xf6420000, 0xf84961e0, 0xf2401000, 0xf2c52000, 0x21000000, 0x1080f8c0,
    0x1084f8c0, 0x1180f8c0, 0x71fbf647, 0xf6406001, 0x21ff6004, 0x0000f2c5, 0x01def2cc, 0xf04f6001,
    0x210240a0, 0xf2407001, 0xf2c00008, 0x44480000, 0xf874f000, 0xbf182800, 0xbd802001, 0x47702000,
    0xf240b580, 0xf2c00008, 0xf2460000, 0x4448636c, 0xf6c62100, 0xf44f3365, 0xf0003260, 0x2800f865,
    0x2001bf18, 0xbf00bd80, 0xf020b580, 0xf2404170, 0xf2c00008, 0xf2460000, 0x4448636c, 0x3365f6c6,
    0x7200f44f, 0xf850f000, 0xbf182800, 0xbd802001, 0xb081b5f0, 0x0708f240, 0x460d4614, 0xf0200441,
    0xf2c04670, 0xd10a0700, 0x636cf246, 0x0007eb09, 0xf6c64631, 0xf44f3365, 0xf0004200, 0xf5b5f835,
    0xbf987f00, 0x7500f44f, 0x0007eb09, 0x46224631, 0xf000462b, 0x2800f82f, 0x2001bf18, 0xbdf0b001,
    0x460cb5b0, 0xf0204605, 0x46114070, 0xf0004622, 0x2800f872, 0x4425bf08, 0xbdb04628, 0x460ab580,
    0x4170f020, 0x0008f240, 0x0000f2c0, 0xf0004448, 0x2800f817, 0x2001bf18, 0x0000bd80, 0x018cf245,
    0x3100f2c1, 0x47086809, 0x3c4ff64a, 0x3c00f2c1, 0xbf004760, 0x3cb5f64a, 0x3c00f2c1, 0xbf004760,
    0x3381f64a, 0x3300f2c1, 0xbf004718, 0x4ca5f64a, 0x3c00f2c1, 0xbf004760, 0x03a0f245, 0x3300f2c1,
    0x4718681b, 0x01a4f245, 0x3100f2c1, 0x47086809, 0x01a8f245, 0x3100f2c1, 0x47086809, 0x03acf245,
    0x3300f2c1, 0x4718681b, 0x0cb4f245, 0x3c00f2c1, 0xc000f8dc, 0xbf004760, 0x02b8f245, 0x3200f2c1,
    0x47106812, 0x02bcf245, 0x3200f2c1, 0x47106812, 0x03c0f245, 0x3300f2c1, 0x4718681b, 0x02b0f245,
    0x3200f2c1, 0x47106812, 0x0cc8f245, 0x3c00f2c1, 0xc000f8dc, 0xea404760, 0xb5100301, 0xd10f079b,
    0xd30d2a04, 0xc908c810, 0x429c1f12, 0xba20d0f8, 0x4288ba19, 0x2001d901, 0xf04fbd10, 0xbd1030ff,
    0x07d3b11a, 0x1c52d003, 0x2000e007, 0xf810bd10, 0xf8113b01, 0x1b1b4b01, 0xf810d107, 0xf8113b01,
    0x1b1b4b01, 0x1e92d101, 0x4618d1f1, 0x0000bd10, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
    0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
    0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000
    ],

    # Relative function addresses
    'pc_init': 0x20000021,
    'pc_unInit': 0x2000007d,
    'pc_program_page': 0x200000d1,
    'pc_erase_sector': 0x200000a9,
    'pc_eraseAll': 0x20000081,

    'static_base' : 0x20000000 + 0x00000020 + 0x00000250,
    'begin_stack' : 0x20000500,
    'begin_data' : 0x20000000 + 0x1000,
    'page_size' : 0x200,
    'analyzer_supported' : False,
    'analyzer_address' : 0x00000000,
    'page_buffers' : [0x20001000, 0x20001200],   # Enable double buffering
    'min_program_length' : 0x200,

    # Flash information
    'flash_start': 0x0,
    'flash_size': 0x3D000,
    'sector_sizes': (
        (0x0, 0x8000),
    )
}

class LPC5516(LPC5500Family):

    MEMORY_MAP = MemoryMap(
        FlashRegion(name='nsflash',     start=0x00000000, length=0x3D000, access='rx',
            blocksize=0x200,
            is_boot_memory=True,
            are_erased_sectors_readable=False,
            algo=FLASH_ALGO),
        RomRegion(  name='nsrom',       start=0x03000000, length=0x00020000, access='rx'),
        RamRegion(  name='nscoderam',   start=0x04000000, length=0x00004000, access='rwx',
            default=False),
        RamRegion(  name='nsram',       start=0x20000000, length=0x00010000, access='rwx'),
        RamRegion(  name='usbram',      start=0x20010000, length=0x00004000, access='rwx'),
        )

    def __init__(self, session):
        super(LPC5516, self).__init__(session, self.MEMORY_MAP)
        self._svd_location = SVDFile.from_builtin("LPC5516.xml")
