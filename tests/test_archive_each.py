from __future__ import annotations

import pytest

from cli import app
from scripts import archive_each


@pytest.mark.parametrize('codec', ['zstd', 'lz4'])
@pytest.mark.parametrize('compression', [0, 5])
@pytest.mark.parametrize('cli', [False, True])
def test_archive_each(
    codec,
    compression,
    cli,
    tmp_path,
):
    paths = [tmp_path / x for x in ['ham', 'egg', 'spam']]

    for p in paths:
        p.mkdir()

    if cli:
        app([
            'archive-each',
            str(tmp_path),
            '--subdir',
            '--codec',
            codec,
            '--compression',
            str(compression),
            '--log',
            '2',
        ])
    else:
        conf = archive_each.Config(codec=codec, compression=compression, log=2)
        archive_each.archive_each(paths=paths, subdir=False, conf=conf)

    for p in paths:
        assert p.with_suffix('.7z').exists()
