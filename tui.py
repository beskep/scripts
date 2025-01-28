from __future__ import annotations

import sys
import typing
from pathlib import Path

import argparse_tui.schemas as ts
from argparse_tui import tui

from cli import app
from scripts import archive_each as ae


class Tui(tui.Tui):
    def __init__(
        self,
        directory: str | Path,
        app_name: str = 'script',
        app_version: str | None = None,
        command_filter: str | None = None,
    ):
        self.dir = Path(directory)

        root = ts.CommandSchema(
            ts.CommandName('script'),
            options=[
                ts.OptionSchema(
                    '--debug',
                    bool,
                    value=False,
                    is_flag=True,
                    secondary_opts=['--no-debug'],
                ),
                ts.OptionSchema(
                    '--toast',
                    bool,
                    value=True,
                    is_flag=True,
                    secondary_opts=['--no-toast'],
                ),
            ],
        )

        for cmd in self._commands():
            cmd.parent = root
            root.subcommands[cmd.name] = cmd

        super().__init__(
            {ts.CommandName('script'): root},
            app_name,
            app_version,
            command_filter,
        )

        self.theme = 'nord'

    def _commands(self):
        yield ts.CommandSchema(
            ts.CommandName('resize'),
            options=[
                ts.OptionSchema('--src', str, value=self.dir.as_posix()),
                ts.OptionSchema('--dst', str),
                ts.OptionSchema('--format', str, value='avif'),
                ts.OptionSchema('--size', int, value=0),
                ts.OptionSchema('--filter', str, value='Mitchell'),
                ts.OptionSchema('--quality', int),
                ts.OptionSchema('--extra'),
                ts.OptionSchema(
                    '--batch',
                    bool,
                    value=True,
                    is_flag=True,
                    secondary_opts=['--no-batch'],
                ),
                ts.OptionSchema(
                    '--prefix', default='original', choices=['original', 'resized']
                ),
            ],
        )

        yield ts.CommandSchema(
            ts.CommandName('group-size'),
            options=[
                ts.OptionSchema('--path', str, value=self.dir.as_posix()),
                ts.OptionSchema(
                    '--na',
                    bool,
                    value=False,
                    is_flag=True,
                    secondary_opts=['--drop-na'],
                ),
            ],
        )

        dirs = [x.as_posix() for x in self.dir.glob('*') if x.is_dir()]
        codecs = typing.get_args(ae.Codec)
        yield ts.CommandSchema(
            ts.CommandName('archive-each'),
            options=[
                ts.OptionSchema('--paths', value=dirs, choices=dirs, multiple=True),
                ts.OptionSchema('--codec', default=codecs[0], choices=codecs),
                ts.OptionSchema('--compression', int),
                ts.OptionSchema('--extra'),
            ],
        )

        files = [x.as_posix() for x in self.dir.glob('*') if x.is_file()]
        yield ts.CommandSchema(
            ts.CommandName('loudnorm'),
            options=[
                ts.OptionSchema('--src', str, required=True, choices=files),
                ts.OptionSchema('--dst'),
                ts.OptionSchema(
                    '--codec', default='libopus', choices=['libopus', 'aac']
                ),
                ts.OptionSchema('--ext', placeholder='(`dst` extension)'),
            ],
        )

        yield ts.CommandSchema(
            ts.CommandName('rptl'),
            options=[
                ts.OptionSchema('--path', value=self.dir.as_posix()),
                ts.OptionSchema('--extra'),
            ],
        )

    def _run_command(self):
        if not (self.post_run_command and self.execute_on_exit):
            return

        args = self.post_run_command

        if 'archive-each' in args:
            args = [*args, '--no-subdir']
        elif 'rptl' in args and '--extra' in args:
            idx = args.index('--extra')
            args.pop(idx)
            extra = args.pop(idx)
            args = [*args, *extra.split(' ')]

        app.meta(args)

    def run(self, **kwargs) -> None:
        try:
            super(tui.Tui, self).run(**kwargs)
        finally:
            self._run_command()


if __name__ == '__main__':
    try:
        path = sys.argv[1]
    except IndexError:
        path = '.'

    Tui(path).run()
