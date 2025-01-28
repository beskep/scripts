from __future__ import annotations

from typing import TYPE_CHECKING

from scripts import rptl

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


SCRIPT = """
# Characters
define c1 = Character("character1")
define c2 = Character("character2")
"""

RPY = """
translate korean strings:

    # source.rpy:99
    old "s1"
    new "s2"

# source.rpy:65
translate korean abcdef:

    # c1 "s3"
    c1 "s4"

translate korean strings:

    # source.rpy:99
    old "[character1]"
    new "[character2]"

translate korean strings:

    # source.rpy:99
    old "character1"
    new "character2"

translate korean strings:

    # source.rpy:99
    old "long{p}string{w}"
    new "%translated"
"""


def gen_test_files(d: Path, conf: rptl.Config, paths: rptl.Paths, rpys: Sequence[str]):
    if paths.script is None:
        raise ValueError

    tl = d / paths.tl / conf.language
    tl.mkdir(parents=True)

    (d / paths.script).write_text(SCRIPT)

    for rpy in rpys:
        (tl / rpy).write_text(RPY)


def test_rptl(tmp_path):
    conf = rptl.Config(linebreak_threshold=10, dev_mode=True)
    paths = rptl.Paths()

    rpys = ['gui.rpy', 'scenario.rpy']

    gen_test_files(tmp_path, conf=conf, paths=paths, rpys=rpys)
    rt = rptl.RenpyTranslation(tmp_path, conf=conf, paths=paths)
    rt()

    assert rt.characters == {'character1', 'character2'}

    dev_script = (tmp_path / paths.dev_mode).read_text()
    assert dev_script == conf.dev_script

    tl = tmp_path / paths.tl / conf.language
    for rpy in rpys:
        text = (tl / rpy).read_text()

        if rpy == 'gui.rpy':
            assert '"s1"' in text
            assert '"s3"' in text
        else:
            assert 's1  |  s2' in text
            assert 's3  |  s4' in text

            assert 'new "[character1]"' in text
            assert 'character1 (character2)' in text

            assert 'long / string\\n%%translated' in text
