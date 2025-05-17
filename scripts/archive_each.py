from __future__ import annotations

import dataclasses as dc
import os
import shutil
import subprocess as sp
from typing import TYPE_CHECKING, ClassVar, Literal

import rich
from loguru import logger
from rich.panel import Panel

from scripts.utils.terminal import Progress

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


Codec = Literal['zstd', 'brotli', 'lz4', 'lz5', 'lizard', 'flzma2']
LogLevel = Literal[0, 1, 2]


@dc.dataclass
class Config:
    codec: Codec = 'zstd'

    extension: str | None = '7z'
    """압축파일 확장자. `auto`면 코덱에 따라 선택."""

    compression: int = 0
    """압축 레벨. 1에서 9 사이 또는 0 (nanazipc 기본값)."""

    log: LogLevel = 0
    """로그 레벨."""

    extra: str | None = None
    """기타 nanazipc 옵션."""

    def get_args(self):
        for arg in [
            f'-bso{self.log}',
            f'-m0={self.codec}',
            None if self.compression == 0 else f'-mx{self.compression}',
            *(self.extra or '').split(' '),
        ]:
            if arg:
                yield arg


@dc.dataclass
class DirArchive:
    nanazipc: dc.InitVar[str | Path | None] = None
    conf: Config = dc.field(default_factory=Config)

    console: rich.console.Console = dc.field(default_factory=rich.get_console)
    _nanazipc: str = dc.field(init=False)

    EXTENSION: ClassVar[dict[Codec, str]] = {
        'zstd': 'zst',
        'brotli': 'br',
        'lz4': 'lz4',
        'lz5': 'lz5',
        'lizard': 'liz',
        'flzma2': '7z',
    }

    def __post_init__(self, nanazipc: str | Path | None):
        if (p := nanazipc or shutil.which('nanazipc')) is None:
            msg = 'Cannot find NanaZipC'
            raise FileNotFoundError(msg)

        self._nanazipc = str(p)

    def _args(self, d: Path) -> list[str]:
        if not d.is_dir():
            raise NotADirectoryError(d)

        ds = d.as_posix().rstrip('/')
        ext = (
            self.EXTENSION.get(self.conf.codec, '7z')
            if (self.conf.extension is None or self.conf.extension == 'auto')
            else self.conf.extension
        ).lstrip('.')

        return [
            self._nanazipc,
            'a',
            *self.conf.get_args(),
            '-sccUTF-8',
            f'{ds}.{ext}',
            f'{ds}/*',
        ]

    def print_panel(self, b: bytes, **kwargs):
        if s := b.decode().strip():
            self.console.print(Panel(s, highlight=True, **kwargs))

    def archive(self, d: Path):
        args = self._args(d)

        try:
            p = sp.run(args, capture_output=True, check=True)
        except sp.CalledProcessError as e:
            self.print_panel(e.stderr, title='Error')
            raise

        self.print_panel(p.stdout, title='stdout')
        self.print_panel(p.stderr, title='stderr')

    def archive_each(self, *args: Path):
        common = os.path.commonpath(args) if len(args) > 1 else None

        for d in Progress.iter(args, description='Archiving...'):
            logger.info('target="{}"', d.relative_to(common) if common else d)
            self.archive(d)


def archive_each(paths: Sequence[Path], *, subdir: bool = False, conf: Config):
    match len(paths), subdir:
        case 1, True:
            paths = [x for x in paths[0].glob('*') if x.is_dir()]
        case 1, False:
            pass
        case _, True:
            logger.warning('`subdir`를 지정했으나 하나 이상의 경로를 입력했습니다.')

    if not paths:
        msg = '대상 폴더가 지정되지 않음.'
        raise FileNotFoundError(msg)

    for path in paths:
        if not path.is_dir():
            raise NotADirectoryError(path)

    DirArchive(conf=conf).archive_each(*paths)
