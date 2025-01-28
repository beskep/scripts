from __future__ import annotations

import abc
import dataclasses as dc
import shutil
import subprocess as sp
from itertools import chain
from typing import TYPE_CHECKING, Any, ClassVar, Literal

import rich
from loguru import logger

from scripts.utils.bytes_unit import BytesUnit
from scripts.utils.terminal import Progress

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


class ResizedDirectoryError(ValueError):
    pass


class NoImagesError(FileNotFoundError):
    def __init__(self, path, message='No images in "{}"') -> None:
        self.path = path
        self.message = message.format(path)
        super().__init__(self.message)


def _bytes(size: float):
    fs = BytesUnit(size)
    return f'{fs.size: 6.1f} {fs.unit}'


@dc.dataclass
class ResizeConfig:
    format: str | None = 'avif'

    size: int | str = 0
    """가로/세로 가장 작은 축 크기. 0이면 원본."""

    filter: str | None = 'Mitchell'
    """Mitchell, Hermite, Lanczos, ..."""

    shrink_only: bool = True

    quality: int | None = None  # XXX avif default quality
    """품질 (0-100)."""

    extra: str | None = None
    """magick 부가 옵션."""

    capture: bool = True
    """capture magick output"""

    warning_threshold: float = 0.9

    _size: str = dc.field(init=False)

    def __post_init__(self):
        self._size = '100%' if self.size == 0 else f'{self.size}x{self.size}'
        if self.shrink_only:
            self._size = f'{self._size}^>'

    def args(self):
        values = [True, self.format, self.filter, self.quality, self.extra]
        args: list[Any] = [
            ['-resize', self._size],
            ['-format', self.format],
            ['-filter', self.filter],
            ['-quality', str(self.quality)],
            [self.extra],
        ]

        return chain.from_iterable(a for a, v in zip(args, values, strict=True) if v)


@dc.dataclass
class BatchConfig:
    batch: bool = True

    prefix: Literal['original', 'resized'] = 'original'
    prefix_original: str = '≪ORIGINAL≫'
    prefix_resized: str = '≪RESIZED≫'
    prefix_not_reduced: str = '≪NotReduced≫'


class _ImageMagicResizer(abc.ABC):
    IMG_EXTS: ClassVar[set[str]] = {
        '.apng',
        '.avif',
        '.bmp',
        '.gif',
        '.jpeg',
        '.jpg',
        '.jxl',
        '.png',
        '.tiff',
        '.webp',
    }

    def __init__(
        self,
        magick: str | Path | None = None,
        conf: ResizeConfig | None = None,
    ) -> None:
        if (p := magick or shutil.which('magick')) is None:
            msg = 'Cannot find ImageMagick in system path.'
            raise FileNotFoundError(msg)

        self._magick = p
        self._conf = conf or ResizeConfig()

    @classmethod
    def find_images(cls, path: Path):
        return (x for x in path.iterdir() if x.suffix.lower() in cls.IMG_EXTS)

    def get_size(self, path):
        args = [self._magick, 'identify', '-ping', '-format', '%w %h', path]
        size = sp.check_output(args).decode()
        return [int(x) for x in size.split(' ')]

    def scaling_ratio(self, path: Path, size: int) -> Iterable[float]:
        for image in self.find_images(path):
            yield min(1.0, size / min(self.get_size(image)))

    def log(self, src: Path, ss: int, ds: int, size: int | str):
        if ds <= ss * self._conf.warning_threshold:
            level = 'INFO'
        elif ds < ss:
            level = 'WARNING'
        else:
            level = 'ERROR'

        if not isinstance(size, int):
            msg = ''
        else:
            ratio = tuple(self.scaling_ratio(path=src, size=size))
            scaled = sum(1 for x in ratio if x > 0)
            total = len(ratio)

            avg = (
                f'(avg ratio {sum(ratio) / total:5.1%})'
                if scaled
                else '[red italic](NOT scaled)[/]'
            )
            msg = f'Scaled Images {scaled:>3d}/{total:>3d}={scaled / total:4.0%} {avg}'

        # TODO 원본 해상도 통계 출력
        logger.log(
            level,
            'File Size {ss} -> {ds} ({r:6.1%}) | {msg}',
            ss=_bytes(ss),
            ds=_bytes(ds),
            r=ds / ss,
            msg=msg,
        )

    @abc.abstractmethod
    def resize(self, src: Path, dst: Path) -> bool:
        pass


class ConvertResizer(_ImageMagicResizer):
    def __init__(
        self,
        path: str | Path | None = None,
        conf: ResizeConfig | None = None,
    ) -> None:
        super().__init__(magick=path, conf=conf)

        self._args = [self._magick, 'convert', *self._conf.args()]

    def _convert(self, src: Path, dst: Path):
        return sp.run(
            [*self._args, src, dst],
            capture_output=self._conf.capture,
            check=False,
        )

    def resize(self, src: Path, dst: Path):
        if not (images := sorted(self.find_images(src))):
            raise NoImagesError(src)

        ss, ds = 0, 0

        for image in Progress.iter(images, transient=True):
            resized = dst.joinpath(image.name)
            if s := self._conf.format:
                resized = resized.with_suffix(f'.{s}')

            out = self._convert(src=image, dst=resized)
            if not resized.exists():
                raise RuntimeError(out.stderr)

            ss += image.stat().st_size
            ds += resized.stat().st_size

        self.log(src=src, ss=ss, ds=ds, size=self._conf.size)

        return ds < ss


class MogrifyResizer(_ImageMagicResizer):
    def __init__(
        self,
        path: str | Path | None = None,
        conf: ResizeConfig | None = None,
    ) -> None:
        super().__init__(magick=path, conf=conf)

        self._args = [self._magick, 'mogrify', '-verbose', *self._conf.args()]

    @staticmethod
    def _mogrify(args):
        with sp.Popen(args=args, stdout=sp.PIPE, stderr=sp.DEVNULL) as p:
            assert p.stdout is not None
            while p.poll() is None:
                yield p.stdout.readline().decode().strip()

    def resize(self, src: Path, dst: Path):
        args = [*self._args, '-path', dst, f'{src}/*']
        logger.debug(args)

        if not (total := sum(1 for _ in self.find_images(src))):
            raise NoImagesError(src)

        if not self._conf.capture:
            sp.run(args=args, check=False)
        else:
            for line in Progress.iter(
                sequence=self._mogrify(args),
                total=total,
                transient=True,
            ):
                if s := line.strip():
                    logger.debug(s)

        ss = sum(x.stat().st_size for x in src.glob('*'))
        ds = sum(x.stat().st_size for x in dst.glob('*'))
        self.log(src=src, ss=ss, ds=ds, size=self._conf.size)

        return ds < ss


def _resize_dir(
    src: Path,
    dst: Path,
    subdir: Path,
    resizer: _ImageMagicResizer,
    conf: BatchConfig,
):
    logger.info('target="{}"', subdir.name)
    if not any(True for _ in resizer.find_images(subdir)):
        raise NoImagesError(subdir)

    if src != dst:
        s = subdir
        d = dst
    elif conf.prefix == 'original':
        s = src / f'{conf.prefix_original}{subdir.name}'
        d = dst / subdir.name
        subdir.rename(s)
    else:
        if subdir.name.startswith(conf.prefix_resized):
            raise ResizedDirectoryError

        s = subdir
        d = dst / f'{conf.prefix_resized}{subdir.name}'

    d.mkdir(exist_ok=True)
    is_reduced = resizer.resize(src=s, dst=d)

    if not is_reduced:
        d.rename(d.parent / f'{conf.prefix_not_reduced}{d.name}')

    return is_reduced


def resize(
    src: Path,
    dst: Path | None,
    rc: ResizeConfig,
    bc: BatchConfig,
    resizer_type: type[_ImageMagicResizer] | None = None,
):
    if not bc.batch and dst is None:
        msg = 'batch 모드가 아닌 경우 dst를 지정해야 합니다.'
        raise ValueError(msg)

    dst = src if dst is None else dst

    logger.info('src="{}"', src)
    logger.info('dst="{}"', dst)
    logger.info(rc)
    logger.info(bc)
    rich.get_console().rule()

    if bc.batch:
        subdirs: Iterable[Path] = (x for x in src.iterdir() if x.is_dir())
    else:
        subdirs = [src]

    resizer_type = resizer_type or MogrifyResizer
    resizer = resizer_type(conf=rc)

    for subdir in subdirs:
        try:
            _resize_dir(src=src, dst=dst, subdir=subdir, resizer=resizer, conf=bc)
        except ResizedDirectoryError:
            pass
        except NoImagesError as e:
            logger.warning(str(e))
            continue
        except (OSError, RuntimeError, ValueError) as e:
            logger.exception(e)
            break
