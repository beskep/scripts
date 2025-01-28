from __future__ import annotations

import io

import pytest

from cli import app
from scripts.images import group_size

TEXT = r"""제작자ː WizTree 4.23 2025-01-01 00:00:00 (기부하여 이 메시지를 숨길 수 있습니다)
파일 이름,크기,할당된 크기,수정한 날짜,속성,파일,폴더
"C:\Users\User\Downloads\test\",388,0,2025-01-28 13:23:03,0,3,3
"C:\Users\User\Downloads\test\[N／A (na-author)] na-work\",1,1,2025-01-28 13:19:43,16,0,0
"C:\Users\User\Downloads\test\[na-group (N／A)] na-work\",0,0,2025-01-28 13:19:43,16,0,0
"C:\Users\User\Downloads\test\[group4 (author4)] work4.rar",82,0,2025-01-28 13:22:59,32,0,0
"C:\Users\User\Downloads\test\[group3 (author3)] work3.7z",122,0,2025-01-28 13:22:52,32,0,0
"C:\Users\User\Downloads\test\[group2 (author2)] work2.zip",184,0,2025-01-28 13:22:24,32,0,0
"C:\Users\User\Downloads\test\[group1 (author1)] work1\",0,0,2025-01-28 13:19:43,16,0,0
"""  # noqa: E501 RUF001


def test_read():
    src = io.StringIO(TEXT)
    df = group_size.read_wiztree_report(src)
    assert df.height == 6  # noqa: PLR2004


@pytest.mark.parametrize('cli', [False, True])
@pytest.mark.parametrize('viz', ['bar', '42'])
def test_group_size(cli, viz, tmp_path):
    src = tmp_path / 'WizTree.csv'
    src.write_text(TEXT, 'utf-8')

    if viz == '42':
        with pytest.raises(ValueError, match="'42' not in"):
            group_size.group_size(src, viz=viz)
        return

    if cli:
        app(['group-size', str(tmp_path), '--viz', viz])
    else:
        group_size.group_size(src, viz=viz)

    for file in ['Works', 'Works-Group', 'Works-Author']:
        assert (tmp_path / f'{file}.html').exists()
