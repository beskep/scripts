from __future__ import annotations

import dataclasses as dc
from itertools import repeat
from typing import ClassVar


@dc.dataclass
class BytesUnit:
    byte: float

    _: dc.KW_ONLY

    binary: bool = True
    digits: int | None = 2

    size: float = dc.field(init=False)
    unit: str = dc.field(init=False)

    _UNITS: ClassVar[tuple[str, ...]] = (
        'bytes',
        'K',
        'M',
        'G',
        'T',
        'P',
        'E',
        'Z',
        'Y',
    )

    def __post_init__(self):
        self.size, self.unit = self.bytes_unit(byte=self.byte, binary=self.binary)

    def __str__(self) -> str:
        f = f'.{self.digits}f' if self.digits else ''
        return f'{self.size:{f}} {self.unit}'

    @classmethod
    def bytes_unit(cls, byte: float, *, binary=True) -> tuple[float, str]:
        k = 1024.0 if binary else 1000.0
        suffix = 'iB' if binary else 'B'

        for u, s in zip(
            cls._UNITS[:-1],
            ('', *repeat(suffix, len(cls._UNITS) - 2)),
            strict=True,
        ):
            if abs(byte) < k:
                return byte, f'{u}{s}'

            byte /= k

        return byte, f'{cls._UNITS[-1]}{suffix}'
