from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, TypeVar

import rich
from loguru import logger
from rich import progress as pg
from rich.highlighter import Highlighter, RegexHighlighter
from rich.logging import RichHandler
from rich.text import Text
from rich.theme import Theme

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from logging import LogRecord

    from rich.style import StyleType
    from rich.table import Column


__all__ = ['LogHandler', 'Progress']


T = TypeVar('T')

console = rich.get_console()
console.push_theme(Theme({'logging.level.success': 'bold blue'}))


class LogHandler(RichHandler):
    _NEW_LEVELS: ClassVar[dict[int, str]] = {5: 'TRACE', 25: 'SUCCESS'}

    def emit(self, record: LogRecord) -> None:
        if name := self._NEW_LEVELS.get(record.levelno):
            record.levelname = name

        return super().emit(record)

    @classmethod
    def set(
        cls,
        level: int | str = 20,
        *,
        rich_tracebacks: bool = False,
        remove: bool = True,
        **kwargs,
    ) -> None:
        if remove:
            logger.remove()

        handler = cls(
            console=console,
            markup=True,
            log_time_format='[%X]',
            rich_tracebacks=rich_tracebacks,
        )
        logger.add(handler, level=level, format='{message}', **kwargs)

        path = Path(__file__).parents[2] / 'script.log'
        logger.add(
            path,
            level=min(20, level),
            rotation='1 month',
            retention='1 year',
            encoding='UTF-8-SIG',
        )


class ProgressHighlighter(RegexHighlighter):
    highlights = [r'(?P<dim>\d+/\d+=0*)(\d*%)']  # noqa: RUF012


class ProgressColumn(pg.TaskProgressColumn):
    def __init__(
        self,
        *,
        style: StyleType = 'progress.download',
        highlighter: Highlighter | None = None,
        table_column: Column | None = None,
        show_speed: bool = False,
    ) -> None:
        super().__init__(
            text_format='',
            text_format_no_percentage='',
            style=style,
            justify='left',
            markup=True,
            highlighter=highlighter or ProgressHighlighter(),
            table_column=table_column,
            show_speed=show_speed,
        )

    @staticmethod
    def text(task: pg.Task) -> str:
        completed = int(task.completed)
        total = int(task.total) if task.total is not None else '?'
        width = len(str(total))
        return f'{completed:{width}d}/{total}={task.percentage:>03.0f}%'

    def render(self, task: pg.Task) -> Text:
        if task.total is None and self.show_speed:
            return self.render_speed(task.finished_speed or task.speed)

        s = self.text(task=task)
        text = Text(s, style=self.style, justify=self.justify)

        if self.highlighter:
            self.highlighter.highlight(text)

        return text


class Progress(pg.Progress):
    @classmethod
    def get_default_columns(cls) -> tuple[pg.ProgressColumn, ...]:
        return (
            pg.TextColumn('[progress.description]{task.description}'),
            pg.BarColumn(bar_width=60),
            ProgressColumn(show_speed=True),
            pg.TimeRemainingColumn(compact=True, elapsed_when_finished=True),
        )

    @classmethod
    def iter(
        cls,
        sequence: Sequence[T] | Iterable[T],
        *,
        description: str = 'Working...',
        total: float | None = None,
        completed: int = 0,
        transient: bool = False,
    ) -> Iterable[T]:
        with cls(transient=transient) as p:
            yield from p.track(
                sequence,
                total=total,
                completed=completed,
                description=description,
            )


if __name__ == '__main__':
    import time

    for _ in Progress.iter(list(range(10))):
        time.sleep(0.1)

    LogHandler.set(1, rich_tracebacks=False)

    logger.trace('Trace')
    logger.debug('Debug')
    logger.info('Info')
    logger.success('Success')
    logger.warning('Warning')
    logger.error('Error')
    logger.critical('Critical')

    try:
        x = 1 / 0
    except ZeroDivisionError as e:
        logger.exception(e)
