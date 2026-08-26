// Managed by Ansible (roles/tgpio_pps).
//
// The Mu's TGPIO beta BIOS (LP-BS-S70NC1R200-*-TGPIO, AMI 5.27 07/19/2024)
// gates the TIME_SYNC ACPI devices on two GNVS bytes, TGEA/TGEB, that its
// POST code is supposed to seed from the "Enable Timed GPIO0/1" setup
// options (PchSetup 0x742/0x743). Those options are Enabled in every NVRAM
// copy, but the seeding is nondeterministic: the gates have flipped in both
// directions across unattended warm reboots with identical NVRAM, so on
// most boots INTC1024 never appears and pin 123 goes silent. The TIME_SYNC1
// block itself (PWRM+0x1310) and the GPP_B14 pad mux are programmed
// unconditionally -- only the ACPI device declaration is missing.
//
// This SSDT re-declares the device so intel-pps-gen-tio can bind. It is
// loaded by the kernel's ACPI table-upgrade mechanism from an early-initrd
// cpio (see tasks/main.yml), before enumeration, on every boot.
//
// _STA is the inverse of the firmware gate: on a boot where the BIOS
// happens to seed TGEB=1, the DSDT's own \_SB.TGI1 is present and this
// device hides itself, so the two declarations can never both claim
// PWRM+0x1310. \TGEB resolves against the DSDT's GNVS field block, which
// is always loaded before this table.
DefinitionBlock ("", "SSDT", 2, "PTPEXP", "TGPIO1", 0x00000002)
{
    External (\TGEB, FieldUnitObj)

    Scope (\_SB)
    {
        Device (TGF1)
        {
            Name (_HID, "INTC1024")  // TIME_SYNC1 -> GPP_B14 = Mu pin 123
            Name (_STR, Unicode ("Timed GPIO 2 (BIOS gate bypass)"))
            Method (_STA, 0, NotSerialized)
            {
                If ((\TGEB == One))
                {
                    Return (Zero)
                }

                Return (0x0F)
            }

            Name (_CRS, ResourceTemplate ()
            {
                Memory32Fixed (ReadWrite,
                    0xFE001310,         // PWRM (0xFE000000) + TIME_SYNC1 0x1310
                    0x00000038,
                    )
            })
        }
    }
}
