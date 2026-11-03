# Chirp brand assets

An original bird-on-a-branch icon drawn by `scripts/generate_brand.py` on a
dark navy rounded square, with a matching gold `Chirp` wordmark for the
landscape logo. No third-party artwork is used.

| File | Size | Purpose |
| --- | --- | --- |
| `icon.png` | 256 × 256 | Home Assistant and HACS icon |
| `icon@2x.png` | 512 × 512 | High-resolution icon |
| `logo.png` | 851 × 256 | Landscape integration logo; README artwork |
| `logo@2x.png` | 1703 × 512 | High-resolution landscape logo |

All images are RGBA PNGs with transparent outer corners and backgrounds. These
sizes follow the [HA brand image guidelines](https://contributors.home-assistant.io/core/integrations/brands/).
Home Assistant 2026.3 and later serves these assets from the integration's local
`brand/` directory. The gold wordmark works against light and dark backgrounds,
so separate dark variants are not required.

## Source and permission

The icon is drawn from geometric primitives in this repository's
`scripts/generate_brand.py` and is covered by the repository's MIT license
(Copyright (c) 2026 eigger). The wordmark is rendered with Pillow's bundled
Aileron Regular via
[`ImageFont.load_default`](https://pillow.readthedocs.io/en/stable/reference/ImageFont.html#PIL.ImageFont.load_default).
[Aileron](https://dotcolon.net/font/aileron/) permits commercial use and is
released with no rights reserved. No font file is redistributed or loaded from
the system. The Chirp server's own branding is not reused.

## Reproduce

Use Python 3.10 or newer and Pillow 12.3.0 (also supplied by HA 2026.10.2):

```sh
python -m pip install Pillow==12.3.0
python scripts/generate_brand.py
```

The script needs no network access and produces the same PNG bytes on every
run with that Pillow version.

SHA256 (Pillow 12.3.0):

- `icon@2x.png`: `24b2002ac3c1f1d4fbd101237e13fa2d6d1604d975e3171dec914c2b21f33845`
- `icon.png`: `89bb260f6ec6e919452c591f8be4d9df59b1d4cf3ee3681b491e2a7de08d6287`
- `logo@2x.png`: `7cdb2ece5efaf50959190ec2068c906e54eddcd6f0c7f0adc119eecbcac472cd`
- `logo.png`: `fbf51181e386942562650648b773219a4c60af8fb0d96b6b592ed44d194449a6`

The local `brand/icon.png` is used by the
[HACS brands check](https://hacs.xyz/docs/publish/include/#check-brands).
These files do not imply inclusion in the HACS default list or HA brands
repository. README pages use `custom_components/chirp/brand/logo.png`.
