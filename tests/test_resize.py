from __future__ import annotations

import dataclasses as dc
import shutil
from typing import ClassVar

import numpy as np
import pytest
from PIL import Image, ImageFilter

from cli import app
from scripts.images import resize


@dc.dataclass
class ImageGenerator:
    n: int = 100
    upscale: int = 2
    rng: np.random.Generator = dc.field(default_factory=np.random.default_rng)

    FORMATS: ClassVar[tuple[str, ...]] = ('jpg', 'jpeg', 'png', 'bmp')
    LOSSLESS: ClassVar[tuple[str, ...]] = ('png', 'bmp')

    def __call__(self, n: int = 0, upscale: int = 0):
        n = n or self.n
        upscale = upscale or self.upscale
        arr = self.rng.random([n, n]) * 100 + 100
        return (
            Image.fromarray(arr.astype(np.uint8))
            .resize([n * upscale, n * upscale], resample=Image.Resampling.BOX)
            .filter(ImageFilter.BLUR)
        )


@pytest.mark.parametrize(
    ('fmt', 'resizer_type'),
    [
        ('avif', None),
        ('webp', None),
        ('webp', resize.ConvertResizer),
    ],
)
def test_resize(fmt, resizer_type, tmp_path_factory):
    assert shutil.which('magick')

    rc = resize.ResizeConfig(format=fmt)
    bc = resize.BatchConfig(batch=False)

    gen = ImageGenerator()
    src = tmp_path_factory.mktemp('src')
    dst = tmp_path_factory.mktemp('dst')

    for f in gen.FORMATS:
        gen().save(src / f'{f}.{f}')

    resize.resize(src=src, dst=dst, rc=rc, bc=bc, resizer_type=resizer_type)

    for f in gen.FORMATS:
        assert (dst / f'{f}.{fmt}').exists()


@pytest.mark.parametrize(
    ('prefix', 'resizer_type'),
    [
        ('original', None),
        ('resized', None),
        ('resized', resize.ConvertResizer),
    ],
)
def test_batch_resize(prefix, resizer_type, tmp_path_factory):
    assert shutil.which('magick')

    rc = resize.ResizeConfig(format='webp', size=10, quality=90)
    bc = resize.BatchConfig(batch=True, prefix=prefix)

    gen = ImageGenerator()
    subdirs = ['sub0', 'sub1']

    src = tmp_path_factory.mktemp('src')

    for subdir in subdirs:
        s = src / subdir
        s.mkdir()
        for f in gen.LOSSLESS:
            gen().save(s / f'{f}.{f}')

    resize.resize(src=src, dst=None, rc=rc, bc=bc, resizer_type=resizer_type)

    for subdir in subdirs:
        if prefix == 'original':
            s = src / f'{bc.prefix_original}{subdir}'
            d = src / subdir
        else:
            s = src / subdir
            d = src / f'{bc.prefix_resized}{subdir}'

        assert s.exists()
        assert d.exists()

        for f in gen.LOSSLESS:
            assert (s / f'{f}.{f}').exists()
            assert (d / f'{f}.webp').exists()


def test_resize_cli(tmp_path_factory):
    assert shutil.which('magick')

    gen = ImageGenerator()
    subdirs = ['sub0', 'sub1']

    src = tmp_path_factory.mktemp('src')

    for subdir in subdirs:
        s = src / subdir
        s.mkdir()
        for f in gen.LOSSLESS:
            gen().save(s / f'{f}.{f}')

    app([
        'resize',
        '--src',
        str(src),
        '--format',
        'webp',
        '--size',
        '50',
        '--quality',
        '90',
    ])

    for subdir in subdirs:
        for f in gen.LOSSLESS:
            assert (src / subdir / f'{f}.webp').exists()
