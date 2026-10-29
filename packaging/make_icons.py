"""Make the app icons (Windows .ico, macOS .icns) from the pet's PNG icon. Needs Pillow.
    python packaging/make_icons.py            -> packaging/build_icons/DesktopPets3D.ico / .icns
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'pets', 'sun_conure', 'icon.png')
OUT = os.path.join(HERE, 'build_icons')


def make():
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    img = Image.open(SRC).convert('RGBA')
    ico = os.path.join(OUT, 'DesktopPets3D.ico')
    img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icns = os.path.join(OUT, 'DesktopPets3D.icns')
    try:
        img.resize((512, 512), Image.LANCZOS).save(icns)
    except Exception as e:                      # older Pillow without ICNS writing: build without an icon
        print('icns not written:', e)
        icns = None
    return ico, icns


if __name__ == '__main__':
    print(make())
    sys.exit(0)
