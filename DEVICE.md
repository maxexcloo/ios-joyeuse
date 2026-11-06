# Device

Test device for the ios-miatoll port. Values marked (unverified) have not been read from a phone in this session.

## Hardware

| Field | Value |
|---|---|
| Model | Xiaomi Redmi Note 9 Pro |
| Codename | `joyeuse` (family `miatoll`: curtana, joyeuse, excalibur, gram) |
| SoC | Qualcomm Snapdragon 720G (SM7125, "Atoll") |
| GPU | Adreno 618 |
| Wi-Fi/BT | WCN3990 |
| RAM | 6 GiB (3 banks: 2 GiB @ `0x80000000`, 4 GiB @ `0x100000000`, 1 GiB @ `0x200000000`) |
| Display | 1080x2400 LCD, `ft8756` (Huaxing) or `nt36675` (Tianma) panel |
| Touch | FocalTech FT8756 on QUP SE11 SPI (TLMM gpio53-56) |
| Shipped with | Android 10 |

## Software (stock, as currently installed)

| Field | Value |
|---|---|
| Bootloader | Stock Xiaomi ABL, **unlocked** |
| Boot image header | v2, base 0, kernel `0x8000`, ramdisk `0x1000000`, tags `0x100`, dtb `0x1f00000`, page 4096 |
| Stock header os_version | Android 15.0.0 / 2026-09 (`0x1e0001a9`) |

## Lock state

| Field | Value | Meaning |
|---|---|---|
| Bootloader | unlocked | `fastboot boot` works; nothing needs flashing to test |

## Notes

- The whole family shares the Atoll platform: stock miatoll DTB has GIC `0x17a00000`, UFS `0x1d84000`, SPMI
  `0xc440000`, TLMM `0x3400000`, splash framebuffer `0x9c000000` — all identical to `sweet`. That is why the sweet
  MMIO constants work unmodified, and `tools/mkadt.py --device miatoll` only changes identity strings and the DRAM
  window.
- The touch controller differs by BOM: the stock DT's `synaptics_tcm@20` on SE7 I2C is a variant overlay. The fitted
  part is the FT8756 on SE11 SPI, which patch 0098 drives.
- Panel differs by BOM (`ft8756` Huaxing, `nt36675` Tianma). Neither is driven directly: the port uses the framebuffer
  ABL leaves running, so the bootloader splash persists into iOS.
