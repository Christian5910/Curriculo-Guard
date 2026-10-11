"""Gera os PNGs e o .ico do aplicativo a partir de icon.svg (única fonte).

Uso, a partir da raiz do projeto:
    python assets/make_icons.py

Só depende de pymupdf. Cada tamanho é renderizado direto do SVG (não reduzido de um
PNG maior), para manter as linhas nítidas nos tamanhos pequenos.
"""
import struct
from pathlib import Path
import pymupdf

FOLDER = Path(__file__).resolve().parent
SIZES = (16, 32, 48, 64, 128, 256, 512)
ICO_SIZES = (16, 32, 48, 64, 128, 256)


def render(svg_bytes, size):
    """PNG com fundo transparente do SVG, em `size` x `size` pixels."""
    with pymupdf.open(stream=svg_bytes, filetype='svg') as doc:
        page = doc[0]
        scale = size / page.rect.width
        return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=True).tobytes('png')


def build_ico(images):
    """Monta um .ico com entradas PNG (aceito pelo Windows Vista em diante)."""
    header = struct.pack('<HHH', 0, 1, len(images))
    entries, blobs, offset = b'', b'', 6 + 16 * len(images)
    for size, png in images:
        entries += struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(png), offset)
        blobs += png; offset += len(png)
    return header + entries + blobs


def main():
    svg = (FOLDER / 'icon.svg').read_bytes()
    rendered = {size: render(svg, size) for size in SIZES}
    for size, png in rendered.items():
        (FOLDER / f'icon_{size}.png').write_bytes(png)
    (FOLDER / 'icon.ico').write_bytes(build_ico([(size, rendered[size]) for size in ICO_SIZES]))
    print('gerados:', ', '.join(f'icon_{size}.png' for size in SIZES) + ', icon.ico')


if __name__ == '__main__':
    main()
