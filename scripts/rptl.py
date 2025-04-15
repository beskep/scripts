from __future__ import annotations

import dataclasses as dc
import re
import shutil
from functools import cached_property
from itertools import batched, chain
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from scripts.utils.terminal import Progress

if TYPE_CHECKING:
    from collections.abc import Collection


PERCENT = re.compile(r'(?<!%)(%)(?!%)')
PRESERVE_FILES = {'gui', 'screens'}
PRESERVE_WORDS = {
    'About',
    'After Choices',
    'Auto',
    'Back',
    'Disable',
    'Display',
    'Enter',
    'Escape',
    'Fullscreen',
    'Help',
    'History',
    'Load',
    'Main Menu',
    'Menu',
    'No',
    'Preference',
    'Preferences',
    'Prefs',
    'Q.Load',
    'Q.Save',
    'Quit',
    'Return',
    'Rollback Side',
    'Save',
    'Skip',
    'Space',
    'Start',
    'Tab',
    'Transitions',
    'Unseen Text',
    'Window',
    'Yes',
}

DEV_SCRIPT = """
init 9999 python:
    config.developer = True
    config.console = True

    if 'mousedown_5' not in config.keymap['dismiss']:
        config.keymap['dismiss'].append('mousedown_5')

    try:
        config.underlay[0].keymap['quickSave'] = QuickSave()
        config.keymap['quickSave'] = 'K_F5'
    except:
        pass

    try:
        config.underlay[0].keymap['quickLoad'] = QuickLoad()
        config.keymap['quickLoad'] = 'K_F9'
    except:
        pass
"""


@dc.dataclass(frozen=True)
class RpyReader:
    path: str | Path
    n: int = 100

    def iter_chunk(self):
        lines: list[str] = []

        with Path(self.path).open('r', encoding='UTF-8') as f:
            for line in f:
                lines.append(line)

                if not line.strip():
                    yield lines
                    lines = []

        yield lines

    def __iter__(self):
        for lines in batched(self.iter_chunk(), n=self.n):  # noqa: B911
            yield ''.join(chain.from_iterable(lines))


@dc.dataclass
class TranslationMatch:
    match: re.Match
    full: str
    head: str
    src: str
    dst: str

    def __post_init__(self):
        # % 하나만 존재하는 경우 %%로 변경
        self.dst = PERCENT.sub(r'%%', self.dst)


@dc.dataclass(frozen=True)
class Pattern:
    translation: Collection[str] = (
        # e.g.
        #    old "src"
        #    new "dst"
        r'(?P<head>old \"(?P<src>.*)\"(\s+)new )\"(?P<dst>.*)\"',
        # e.g.
        #    # character "src"
        #    character "dst"
        r'(?P<head># (?P<char>[\w_]*)\s*\"(?P<src>.*)\"(\s+)(?P=char) )\"(?P<dst>.*)\"',
    )

    # `script.rpy` 파일에 있는 캐릭터 목록
    character: str = r'.*Character\(\"(.+?)\".*'

    # translate [language] ...:
    language: tuple[str, str] | None = None

    @cached_property
    def patterns(self):
        return tuple(re.compile(p) for p in self.translation)

    def iter_tl(self, text: str):
        for match in chain.from_iterable(p.finditer(text) for p in self.patterns):
            yield TranslationMatch(match, *match.group(0, 'head', 'src', 'dst'))


@dc.dataclass(frozen=True)
class Paths:
    tl: str = 'game/tl'
    script: str | None = 'game/script.rpy'
    characters: str | None = None
    """캐릭터 정보가 저장된 rpy. 미지정 시 `script`에서 탐색."""

    dev_mode: str = 'game/__dev_mode.rpy'
    backup: str | None = 'Backup'


@dc.dataclass(frozen=True)
class Preserve:
    # 번역하지 않을 파일, 단어 목록
    files: set[str] = dc.field(default_factory=lambda: PRESERVE_FILES)
    words: set[str] = dc.field(default_factory=lambda: PRESERVE_WORDS)


@dc.dataclass(frozen=True)
class Config:
    language: str = 'korean'

    batch_size: int = 100
    linebreak_threshold: int = 12

    dev_mode: bool = True
    # cyclopts 디폴트값 표시 방지
    dev_script: str = dc.field(default_factory=lambda: DEV_SCRIPT)

    preserve: Preserve = dc.field(default_factory=Preserve)


@dc.dataclass(frozen=True)
class RenpyTranslation:
    path: Path

    conf: Config = dc.field(default_factory=Config)
    paths: Paths = dc.field(default_factory=Paths)

    pattern: Pattern = dc.field(default_factory=Pattern)

    @cached_property
    def characters(self) -> set[str]:
        if not (rpy := self.paths.characters or self.paths.script):
            return set()

        if not (path := self.path / rpy).exists():
            raise FileNotFoundError(path)

        text = path.read_text('UTF-8')
        return {m.group(1) for m in re.finditer(self.pattern.character, text)}

    def _edit_side_by_side(self, text: str, m: TranslationMatch) -> str | None:
        """
        원문, 번역 복수 표기

        Parameters
        ----------
        text : str
        m : TranslationMatch

        Returns
        -------
        str | None
        """
        # 캐릭터 이름
        if m.src.strip('[]') in self.characters:
            if re.match(r'^\[.*\]$', m.src):
                # "[캐릭터]" -> 원문 유지
                return text.replace(m.full, f'{m.head}"{m.src}"')

            # 대사창 표기: "원문 (번역)"
            return text.replace(m.full, f'{m.head}"{m.src} ({m.dst})"')

        # 짧은 글
        if len(m.src) <= self.conf.linebreak_threshold:
            return text.replace(m.full, f'{m.head}"{m.src}  |  {m.dst}"')

        src = m.src.replace('{w}', '').replace('{p}', ' / ')  # 원문 줄바꿈 제거

        if not m.dst.startswith(src):
            # 일반 대사: "원문\n번역"
            return text.replace(m.full, f'{m.head}"{src}\\n{m.dst}"')

        return None

    def _edit(
        self,
        text: str,
        m: TranslationMatch,
        *,
        preserve: bool,
    ) -> str | None:
        if (
            m.dst.startswith(m.src)  # fmt
            or (m.src.startswith('old:') and m.dst.startswith('new:'))
        ):
            return None

        # 원문 유지
        if preserve or m.src.strip().strip('.') in self.conf.preserve.words:
            return text.replace(m.full, f'{m.head}"{m.src}"')

        return self._edit_side_by_side(text=text, m=m)

    def _rpy(self, text: str, *, preserve: bool):
        for match in self.pattern.iter_tl(text):
            if t := self._edit(text=text, m=match, preserve=preserve):
                text = t

        return text

    def rpy(self, path: Path):
        preserve = path.stem in self.conf.preserve.files

        reader = RpyReader(path=path, n=self.conf.batch_size)
        texts = (self._rpy(text=text, preserve=preserve) for text in reader)
        return ''.join(texts)

    def __call__(self):
        tl = self.path / self.paths.tl
        language = tl / self.conf.language

        # backup
        backup = tl / f'{self.conf.language}{self.paths.backup}'
        if self.paths.backup and not backup.with_suffix('.zip').exists():
            logger.info('backup="{}"', backup)
            shutil.make_archive(base_name=str(backup), format='zip', root_dir=language)

        # rpy
        if not (paths := list(language.rglob('*.rpy'))):
            raise FileNotFoundError(language)

        for rpy in Progress.iter(paths):
            logger.debug(rpy.relative_to(tl))

            text = self.rpy(rpy)
            if rpy.read_text('UTF-8') != text:
                rpy.write_text(text, 'UTF-8')
                rpy.with_suffix('.rpyc').unlink(missing_ok=True)

        # developer mode
        if not self.conf.dev_mode:
            return

        dev = (self.path / self.paths.dev_mode).with_suffix('.rpy')
        if dev.exists():
            logger.warning('dev mode already exists: "{}"', dev)
        else:
            logger.info('dev_mode="{}"', dev)
            dev.write_text(self.conf.dev_script, 'UTF-8')
