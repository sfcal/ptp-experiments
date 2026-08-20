## Binaries for my Timecard

These are from the OCP TAP, commit: 0ac7df5

Driver must be loaded to flash these

```
$ dmesg | grep ptp_ocp | head -1
[   21.527678] ptp_ocp 0000:10400.0: enabling device (0140 -> 0142)
$ cp TimeCard.bin /lib/firmware
$ devlink dev flash pci/0000:04:00.0 file TimeCard.bin
```

You should probably only use Factory_TimeCard.bin or TimeCard.bin (PTM)