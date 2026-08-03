# SPDX-License-Identifier: GPL-2.0
# Copyright (c)  2018 Intel Corporation
#
# Intel(R) I225-LM/I225-V/I226 2.5G Ethernet Controller
# Out-of-tree build of the kernel v7.0 igc driver with TimeNIC PPS fixes:
#   - EXTTS: rising-edge-only filtering (GPS PPS input)
#   - PEROUT: 1PPS aligned to PHC second boundary (target-time mode)
#   - Module params: edge_check_delay_us, edge_check_invert
#

ifneq ($(KERNELRELEASE),)
obj-m := igc.o
igc-y := igc_main.o igc_mac.o igc_i225.o igc_base.o igc_nvm.o igc_phy.o \
	 igc_diag.o igc_ethtool.o igc_ptp.o igc_dump.o igc_tsn.o igc_xdp.o
igc-$(CONFIG_IGC_LEDS) += igc_leds.o
else
KDIR ?= /lib/modules/$(shell uname -r)/build
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
endif
