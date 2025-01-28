# ruff: noqa: PLC0415

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import Annotated, Literal

import cyclopts
import rich
import windows_toasts as wt
from cyclopts import Parameter
from loguru import logger

from scripts import archive_each as ae
from scripts import rptl
from scripts.images import resize as ir
from scripts.utils.terminal import LogHandler

app = cyclopts.App(
    config=cyclopts.config.Toml('config.toml'),
    help_format='markdown',
)
app.meta.group_parameters = cyclopts.Group('Options', sort_key=0)


@app.meta.default
def launcher(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    debug: bool = False,
    toast: bool = True,
):
    LogHandler.set(level=10 if debug else 20)
    logger.debug(tokens)

    app(tokens)

    if not tokens:
        return

    logger.info('Completed {}', tokens[0])

    if toast:
        wt.WindowsToaster('Script').show_toast(
            wt.Toast(
                [f'Completed {tokens[0]}'],
                duration=wt.ToastDuration.Short,
            ),
        )


_RESIZE_CONF = ir.ResizeConfig()
_BATCH_CONF = ir.BatchConfig()


@app.command(group='Images')
def resize(
    src: Path,
    dst: Path | None = None,
    *,
    rc: Annotated[ir.ResizeConfig, Parameter(name='*')] = _RESIZE_CONF,
    bc: Annotated[ir.BatchConfig, Parameter(name='*')] = _BATCH_CONF,
):
    """
    ImageMagick 이용 폴더별 영상 형식·해상도 변환.

    Parameters
    ----------
    src : Path
    dst : Path | None, optional
    rc : ir.ResizeConfig, optional
    bc : ir.BatchConfig, optional
    """
    ir.resize(src=src, dst=dst, rc=rc, bc=bc)


@app.command(group='Images')
def group_size(
    path: Path,
    *,
    viz: Literal['bar', 'gradient'] = 'bar',
    na: Annotated[bool, Parameter(negative_bool='drop-')] = False,
):
    """그룹별 용량, 폴더·파일 개수 시각화."""
    from scripts.images.group_size import group_size

    group_size(path=path, viz=viz, drop_na=not na)


_ARCHIVE_CONF = ae.Config()


@app.command
def archive_each(
    paths: list[Path],
    *,
    subdir: Annotated[bool, Parameter(['--subdir', '-s'])] = True,
    conf: Annotated[ae.Config, Parameter(name='*')] = _ARCHIVE_CONF,
):
    """
    nanazipc 이용 폴더 개별 압축

    Parameters
    ----------
    paths : list[Path]
    subdir : bool, optional
        `True`면 paths[0] 아래 모든 폴더 대상
    conf : ae.Config, optional
    """
    ae.archive_each(paths, subdir=subdir, conf=conf)


@app.command
def loudnorm(
    src: Path,
    *,
    dst: Path | None = None,
    codec: Literal['libopus', 'aac'] = 'libopus',
    ext: str | None = None,
    progress: bool = True,
):
    """
    ffmpeg-normalize

    Parameters
    ----------
    src : Path
    dst : Path | None, optional
    codec : Literal['libopus', 'aac'], optional
    ext : str, optional
    progress : bool, optional

    Raises
    ------
    FileExistsError
        dst가 이미 존재할 때
    """
    from ffmpeg_normalize import FFmpegNormalize

    ext = ext or src.suffix
    if not ext.startswith('.'):
        ext = f'.{ext}'

    dst = dst or src.with_name(f'{src.stem}-loudnorm{ext}')
    if dst.exists():
        raise FileExistsError(dst)

    logger.info('src="{}"', src)
    logger.info('dst="{}"', dst)

    norm = FFmpegNormalize(audio_codec=codec, progress=progress)
    norm.add_media_file(str(src), str(dst))
    norm.run_normalization()

    if s := norm.stats:
        rich.print(s)


_RPTL_CONF = rptl.Config()
_RPTL_PATHS = rptl.Paths()


@app.command
def rptl_(
    path: Path,
    *,
    conf: Annotated[rptl.Config, Parameter('*')] = _RPTL_CONF,
    paths: Annotated[rptl.Paths, Parameter('path')] = _RPTL_PATHS,
):
    """
    Renpy 번역 원문·번역어 동시 출력

    Parameters
    ----------
    path : Path
        실행파일이 있는 폴더 경로.
    conf : rptl.Config, optional
    paths : rptl.Paths, optional
    """
    from scripts.rptl import RenpyTranslation

    RenpyTranslation(path=path, conf=conf, paths=paths)()


if __name__ == '__main__':
    app.meta()
