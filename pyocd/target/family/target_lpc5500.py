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

from time import sleep
import logging

from ...core.target import Target
from ...coresight.coresight_target import CoreSightTarget
from ...core.memory_map import (FlashRegion, RamRegion, RomRegion, MemoryMap)
from ...coresight.cortex_m import CortexM
from ...coresight.cortex_m_v8m import CortexM_v8M
from ...debug.svd.loader import SVDFile
from ...utility import timeout, conversion
from ...coresight.ap import (APv1Address, APv2Address, AccessPort)
from ...core import exceptions

FPB_CTRL                = 0xE0002000
FPB_COMP0               = 0xE0002008
DWT_COMP0               = 0xE0001020
DWT_FUNCTION0           = 0xE0001028
DWT_FUNCTION_MATCH      = 0x4 << 0   # Instruction address.
DWT_FUNCTION_ACTION     = 0x1 << 4   # Generate debug event.
DWT_FUNCTION_DATAVSIZE  = 0x2 << 10  # 4 bytes.

PERIPHERAL_BASE_NS = 0x40000000
PERIPHERAL_BASE_S  = 0x50000000

FLASH_CMD               = 0x00034000
FLASH_STARTA            = 0x00034010
FLASH_STOPA             = 0x00034014
FLASH_DATAW0            = 0x00034080
FLASH_INT_STATUS        = 0x00034FE0
FLASH_INT_CLR_STATUS    = 0x00034FE8
FLASH_CMD_READ_SINGLE_WORD = 0x3
FLASH_CMD_MARGIN_CHECK  = 0x6

BOOTROM_MAGIC_ADDR      = 0x50000040

LOG = logging.getLogger(__name__)

class LPC5500Family(CoreSightTarget):

    VENDOR = "NXP"

    def create_init_sequence(self):
        seq = super(LPC5500Family, self).create_init_sequence()
        
        seq.wrap_task('discovery',
            lambda seq: seq
                    .insert_before('find_aps',
                        ('resynchronize_dm_ap', self.resynchronize_dm_ap),
                        ) \
                    .wrap_task('find_components', self._modify_ap1) \
                    .replace_task('create_cores', self.create_lpc55xx_cores) \
                    .insert_before('create_components',
                        ('enable_traceclk', self._enable_traceclk),
                        )
            )
        
        return seq
    
    def resynchronize_dm_ap(self):
        if 2 not in self.aps:
            ap_address = APv1Address(2)
            ap = AccessPort.create(self.dp, ap_address)
        else:
            ap = self.aps[2]

        LOG.debug("Resynchronizing dm_ap")
        value = -1
        while value != 0x002A0000:
            try:
                value = ap.read_reg(0xFC)
            except exceptions.TransferFaultError:
                pass
        # Write DM RESYNC_REQ + CHIP_RESET_REQ
        LOG.debug("Sending resync RQ")
        ap.write_reg(0x00, 0x21)
        value = -1
        while value != 0:
            try:
                value = ap.read_reg(0x00)
            except exceptions.TransferTimeoutError:
                pass
        LOG.debug("Resync success")
        self.start_debug_session()

    def start_debug_session(self):
        if 2 not in self.aps:
            ap_address = APv1Address(2)
            ap = AccessPort.create(self.dp, ap_address)
        else:
            ap = self.aps[2]

        LOG.debug("Starting debug session")
        # Write DM START_DBG_SESSION to REQUEST register (1)
        ap.write_reg(0x04, 0x07)
        value = -1
        while value != 0:
            try:
                value = ap.read_reg(0x08) & 0xFFFF
            except exceptions.TransferTimeoutError:
                pass
        LOG.debug("Debug session start success")

    def _modify_ap1(self, seq):
        # If AP#1 exists we need to adjust it before we can read the ROM.
        if seq.has_task('init_ap.1'):
            seq.insert_before('init_ap.1',
                ('set_ap1_nonsec',        self._set_ap1_nonsec),
                )
        
        return seq

    def _set_ap1_nonsec(self):
        # Make AP#1 transactions non-secure so transfers will succeed.
        self.aps[1].hnonsec = 1

    def create_lpc55xx_cores(self):
        # Make sure AP#0 was detected.
        if 0 not in self.aps:
            LOG.error("AP#0 was not found, unable to create core 0")
            return

        # Create core 0 with a custom class.
        core0 = CortexM_LPC5500(self.session, self.aps[0], self.memory_map, 0)
        core0.default_reset_type = self.ResetType.SW_SYSRESETREQ
        self.aps[0].core = core0
        core0.init()
        self.add_core(core0)
        
        # Create core 1 if the AP is present. It uses the standard Cortex-M core class for v8-M.
        if 1 in self.aps:
            core1 = CortexM_v8M(self.session, self.aps[1], self.memory_map, 1)
            core1.default_reset_type = self.ResetType.SW_SYSRESETREQ
            self.aps[1].core = core1
            core1.init()
            self.add_core(core1)
    
    def _enable_traceclk(self):
        # Don't make it worse if no APs were found.
        if 0 not in self.aps:
            return
        
        SYSCON_NS_Base_Addr = 0x40000000
        IOCON_NS_Base_Addr  = 0x40001000
        TRACECLKSEL_Addr    = SYSCON_NS_Base_Addr + 0x268
        TRACECLKDIV_Addr    = SYSCON_NS_Base_Addr + 0x308
        AHBCLKCTRLSET0_Addr = IOCON_NS_Base_Addr  + 0x220
        
        clksel = self.read32(TRACECLKSEL_Addr)  # Read current TRACECLKSEL value
        if clksel > 2:
            self.write32(TRACECLKSEL_Addr, 0x0) # Select Trace divided clock
        
        clkdiv = self.read32(TRACECLKDIV_Addr) & 0xFF # Read current TRACECLKDIV value, preserve divider but clear rest to enable
        self.write32(TRACECLKDIV_Addr, clkdiv)

        self.write32(AHBCLKCTRLSET0_Addr, (1 << 13)) # Enable IOCON clock

    def trace_start(self):
        # Configure PIO0_10: FUNC - 6, MODE - 0, SLEW - 1, INVERT - 0, DIGMODE - 0, OD - 0
        self.write32(0x40001028, 0x00000046)
        
        self.call_delegate('trace_start', target=self, mode=0)

        # On a reset when ITM is enabled, TRACECLKDIV/TRACECLKSEL will be reset
        # even though ITM will remain enabled -- which will cause ITM stimulus
        # writes to hang in the target because the FIFO will never appear ready.
        # To prevent this, we explicitly (re)enable traceclk.
        self._enable_traceclk()

class CortexM_LPC5500(CortexM_v8M):
    _flash_erased = True

    def is_flash_addr(self, addr, length):
        mem_map = self.get_memory_map()
        region = mem_map.get_region_for_address(addr)
        if (region is None) or (not region.is_flash):
            return False

        return region.contains_range(addr, length=length)

    def is_flash_erased(self, addr, length):
        # If the processor is in Secure state, we have to access the flash controller
        # through the secure alias.
        if self.get_security_state() == Target.SecurityState.SECURE:
            base = PERIPHERAL_BASE_S
        else:
            base = PERIPHERAL_BASE_NS

        # Use the flash programming model to check if the first flash page is readable, since
        # attempted accesses to erased pages result in bus faults. The start and stop address
        # are both set to 0x0 to probe the sector containing the reset vector.
        self.write32(base + FLASH_STARTA, addr>>4) # Program flash word start address to 0x0
        self.write32(base + FLASH_STOPA, (addr + length - 1)>>4) # Program flash word stop address to 0x0
        self.write_memory_block32(base + FLASH_DATAW0, [0x00000000] * 8) # Prepare for read
        self.write32(base + FLASH_INT_CLR_STATUS, 0x0000000F) # Clear Flash controller status
        self.write32(base + FLASH_CMD, FLASH_CMD_MARGIN_CHECK) # Read single flash word

        # Wait for flash word read to finish.
        with timeout.Timeout(5.0) as t_o:
            while t_o.check():
                if (self.read32(base + FLASH_INT_STATUS) & 0x00000004) != 0:
                    break
                sleep(0.01)
        
        # Check for error reading flash word.
        if (self.read32(base + FLASH_INT_STATUS) & 0xB) == 0:
            return False
        return True


    def read_memory(self, addr, transfer_size=32, now=True):
        """! @brief Read an aligned block of 32-bit words."""
        if transfer_size == 8:
            data = self.read_memory_block8(addr, 1)[0]
        elif transfer_size == 16:
            data = conversion.byte_list_to_u16le_list(self.read_memory_block8(addr, 2))[0]
        elif transfer_size == 32:
            data = self.read_memory_block32(addr, 1)[0]
            
        if now:
            return data
        else:
            def read_cb():
                return data
            return read_cb

    def read_memory_block32(self, addr, size):
        """! @brief Read an aligned block of 32-bit words."""
        if self.is_flash_addr(addr, size*4):
            if self.is_flash_erased(addr, size*4):
                return [0xFFFFFFFF] * size

        return self.ap.read_memory_block32(addr, size)

    def read_memory_block8(self, addr, size):
        """! @brief Read a block of unaligned bytes in memory.
        @return an array of byte values
        """
        if self.is_flash_addr(addr, size):
            if self.is_flash_erased(addr, size):
                return [0xFF] * size

        data = self.ap.read_memory_block8(addr, size)
        return self.bp_manager.filter_memory_unaligned_8(addr, size, data)

    def set_reset_catch(self, reset_type=None):
        """! @brief Prepare to halt core on reset."""
        LOG.debug("set reset catch, core %d", self.core_number)

        self._reset_catch_mode = 0

        self._reset_catch_delegate_result = self.call_delegate('set_reset_catch', core=self, reset_type=reset_type)

        # Default behaviour if the delegate didn't handle it.
        if not self._reset_catch_delegate_result:
            self.halt()
            
            # Save CortexM.DEMCR.
            self._reset_catch_saved_demcr = self.read_memory(CortexM.DEMCR)

            # This sequence is copied from the NXP LPC55S69_DFP debug sequence.
            reset_vector = 0xFFFFFFFF
            
            # Clear reset vector catch.
            self.write32(CortexM.DEMCR, self._reset_catch_saved_demcr & ~CortexM.DEMCR_VC_CORERESET)
            
            # Read the reset vector address.
            reset_vector = self.read32(0x00000004)

            # Break on user application reset vector if we have a valid breakpoint address.
            if reset_vector != 0xFFFFFFFF:
                self._flash_erased=False
                print("Code exists in flash!!!")
                self._reset_catch_mode = 1
                self.write32(FPB_COMP0, reset_vector|1) # Program FPB Comparator 0 with reset handler address
                self.write32(FPB_CTRL, 0x00000003)    # Enable FPB
            # No valid user application so use watchpoint to break at end of boot ROM. The ROM
            # writes a special address to signal when it's done.
            else:
                self._flash_erased=True
                print("Flash is empty!!!")
                self._reset_catch_mode = 2
                # self.write32(FPB_COMP0, BOOTROM_MAGIC_ADDR) # Program FPB Comparator 0 with reset handler address
                # self.write32(FPB_CTRL, 0x00000003)    # Enable FPB
                self.dwt.set_watchpoint(BOOTROM_MAGIC_ADDR, 4, Target.WatchpointType.READ_WRITE)
                # self.write32(DWT_FUNCTION0, 0)
                # self.write32(DWT_COMP0, BOOTROM_MAGIC_ADDR)
                # self.write32(DWT_FUNCTION0, (DWT_FUNCTION_MATCH | DWT_FUNCTION_ACTION | DWT_FUNCTION_DATAVSIZE))

            # Read DHCSR to clear potentially set DHCSR.S_RESET_ST bit
            self.read32(CortexM.DHCSR)

    def reset(self, reset_type=None):
        """! @brief Reset the core.

        The reset method is selectable via the reset_type parameter as well as the reset_type
        session option. If the reset_type parameter is not specified or None, then the reset_type
        option will be used. If the option is not set, or if it is set to a value of 'default', the
        the core's default_reset_type property value is used. So, the session option overrides the
        core's default, while the parameter overrides everything.

        Note that only v7-M cores support the `VECTRESET` software reset method. If this method
        is chosen but the core doesn't support it, the the reset method will fall back to an
        emulated software reset.

        After a call to this function, the core is running.
        """
        self.session.notify(Target.Event.PRE_RESET, self)

        reset_type = Target.ResetType.SW_EMULATED

        reset_type = self._get_actual_reset_type(reset_type)

        LOG.debug("reset, core %d, type=%s", self.core_number, reset_type.name)

        self._run_token += 1

        # Give the delegate a chance to overide reset. If the delegate returns True, then it
        # handled the reset on its own.
        print("Doing reset the LPC5500 family way")
        if not self.call_delegate('will_reset', core=self, reset_type=reset_type):
            self._perform_reset(reset_type)

        if self._flash_erased:
            print("Resynchronizing dm_ap")
            self.session.target.resynchronize_dm_ap()
        self.halt()            

        self.call_delegate('did_reset', core=self, reset_type=reset_type)

        # Now wait for the system to come out of reset. Keep reading the DHCSR until
        # we get a good response with S_RESET_ST cleared, or we time out.
        with timeout.Timeout(2.0) as t_o:
            while t_o.check():
                try:
                    dhcsr = self.read32(CortexM.DHCSR)
                    if (dhcsr & CortexM.S_RESET_ST) == 0:
                        break
                except exceptions.TransferError:
                    self.flush()
                    sleep(0.01)

        self.session.notify(Target.Event.POST_RESET, self)

    def clear_reset_catch(self, reset_type=None):
        """! @brief Disable halt on reset."""
        LOG.debug("clear reset catch, core %d", self.core_number)

        self.call_delegate('clear_reset_catch', core=self, reset_type=reset_type)

        if not self._reset_catch_delegate_result:
            # Clear breakpoint or watchpoint.
            if self._reset_catch_mode == 1:
                self.write32(0xE0002008, 0)
            elif self._reset_catch_mode == 2:
                self.write32(DWT_COMP0, 0)
                self.write32(DWT_FUNCTION0, 0)

            # restore vector catch setting
            self.write_memory(CortexM.DEMCR, self._reset_catch_saved_demcr)
