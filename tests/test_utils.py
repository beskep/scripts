from __future__ import annotations

import pytest
from loguru import logger

from scripts.utils import bytes_unit, terminal


@pytest.mark.parametrize(
    ('byte', 'binary', 'size', 'unit'),
    [
        (2**10, True, 1, 'K'),
        (2**20, True, 1, 'M'),
        (10**3, False, 1, 'K'),
        (2 * 10**3, False, 2, 'K'),
    ],
)
def test_bytes_unit(byte, binary, size, unit):
    bu = bytes_unit.BytesUnit(byte=byte, binary=binary, digits=2)

    assert bu.size == size
    assert bu.unit == f'{unit}iB' if binary else f'{unit}B'
    assert str(bu) == f'{size}.00 {bu.unit}'

    assert bytes_unit.BytesUnit.bytes_unit(byte, binary=binary) == (bu.size, bu.unit)


def test_log_handler():
    terminal.LogHandler.set(10)
    logger.debug('debug')
    logger.success('success')


@pytest.mark.parametrize('total', [None, 0])
def test_progress(total):
    for _ in terminal.Progress.iter(list(range(10)), total=total):
        pass
