from __future__ import annotations

import dataclasses as dc
from typing import IO, TYPE_CHECKING, Literal

import pandas as pd
import polars as pl
import rich
from loguru import logger

from scripts.utils.bytes_unit import BytesUnit

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


Viz = Literal['bar', 'gradient']


def find_wiztree_report(root: Path):
    if not (files := list(root.glob('WizTree*'))):
        raise FileNotFoundError(root)

    return min(files, key=lambda x: -x.stat().st_mtime)


def _bytes(size):
    return str(BytesUnit(size, digits=2))


class Expr:
    MIB = 'MiB'
    READABLE = 'HumanReadable'

    _MEBI = 2**20

    mebibyte = pl.col('size').truediv(_MEBI).round(2).alias(MIB)
    readable = pl.col('size').map_elements(_bytes, return_dtype=pl.Utf8).alias(READABLE)


def read_wiztree_report(source: str | Path | IO):
    p = pl.col('_path')
    data = (
        pl.scan_csv(source, skip_rows=1)
        .rename({'파일 이름': 'path', '크기': 'size'})
        .with_columns(pl.col('path').str.len_chars().alias('n_chars'))
        .filter(pl.col('n_chars') != pl.col('n_chars').min())  # filter root dir
        .with_columns(
            pl.col('path')
            .str.extract_groups(r'^.*\\(?<dir>.*?)\\(?<file>[^\\]*\.(?<ext>.*))?$')
            .alias('_path')
        )
        .with_columns(p.struct['ext'].is_in(['zip', '7z', 'rar']).alias('is_archive'))
        .with_columns(
            pl.when('is_archive')
            .then(p.struct['file'])
            .otherwise(p.struct['dir'])
            .alias('work'),
            pl.when('is_archive')
            .then(pl.lit(None))
            .otherwise(p.struct['file'])
            .alias('file'),
        )
    )

    files = data.filter(pl.col('file').is_not_null()).group_by('work').len('files')

    return (
        data.filter(pl.col('file').is_null())
        .join(files, on='work', how='left', validate='1:1')
        .with_columns(
            pl.col('work')
            .str.extract_groups(r'^\[(?<group>.*)\((?<author>.*?)\)]')
            .alias('_group')
        )
        .unnest('_group')
        .select(
            'work',
            pl.col('group').str.strip_chars(),
            pl.col('author').str.strip_chars(),
            'files',
            'size',
            Expr.mebibyte,
            Expr.readable,
        )
        .sort('size', descending=True)
        .collect()
    )


@dc.dataclass
class HtmlStyler:
    viz: Viz = 'bar'
    encoding: str = 'UTF-8-SIG'

    _TEMPLATE: str = """
<html>
  <table>
    <tr style="vertical-align: top">{}</tr>
    <tr style="vertical-align: top">{}</tr>
  </table>
</html>
"""

    def to_html(self, df: pl.DataFrame, subset: str):
        styler = pd.DataFrame(
            # .to_pandas()는 pyarrow 설치 필요
            df.sort(subset, descending=True)
            .fill_null('[null]')
            .to_dict(as_series=False)
        ).style

        match self.viz:
            case 'bar':
                styler = styler.bar(subset=subset)
            case 'gradient':
                styler = styler.background_gradient(subset=subset)
            case _:
                msg = f'{self.viz!r} not in ("bar", "gradient")'
                raise ValueError(msg)

        tar = [{'selector': '', 'props': [('text-align', 'right')]}]
        # https://stackoverflow.com/questions/77801279/pandas-set-table-styles-not-working-for-table-tag
        return (
            styler.format({Expr.MIB: '{:.2f}'})
            .set_table_styles(
                [
                    {
                        'selector': '',
                        'props': 'border-collapse: collapse;',
                    },
                    {'selector': 'tr', 'props': 'border-top: 0.5px solid #8884;'},
                    {
                        'selector': 'td, th',
                        'props': 'padding: 0 10px; vertical-align: top;',
                    },
                ],
            )
            .set_table_styles(
                {
                    Expr.READABLE: tar,
                    'files': tar,
                    'work': [{'selector': '', 'props': 'width: fit-content;'}],
                },
                overwrite=False,
            )
            .to_html()
        )

    def write_df(self, path: Path, df: pd.DataFrame | pl.DataFrame, subset: str):
        text = self.to_html(df=df, subset=subset)
        path.write_text(text, encoding=self.encoding)

    def write_dfs(
        self,
        path: Path,
        df: pd.DataFrame | pl.DataFrame,
        subset: Sequence[str],
    ):
        subset = [x for x in subset if not df.select(pl.col(x).is_null().all()).item()]

        width = 1.0 / len(subset)
        th = ''.join(f'<th style="width: {width:%}">By {x}</th>' for x in subset)

        tds = (self.to_html(df=df, subset=x) for x in subset)
        td = ''.join(f'<td>{x}</td>' for x in tds)

        text = self._TEMPLATE.format(th, td)
        path.write_text(text, encoding=self.encoding)


def _by_group(df: pl.DataFrame, by: str, *, drop_na: bool = True):
    if drop_na:
        df = df.filter(pl.col(by) != 'N／A')  # noqa: RUF001

    return (
        df.with_columns(pl.col(by).fill_null('NA'))
        .group_by(by)
        .agg(
            pl.sum('files').replace({0: None}).alias('files'),
            pl.count('size').alias('works'),
            pl.sum('size'),
        )
        .with_columns(Expr.mebibyte, Expr.readable)
        .sort('size', descending=True)
    )


def group_size(path: Path, *, viz: Viz = 'bar', drop_na=True):
    HtmlStyler.viz = viz

    # 대상 파일 찾기
    path = find_wiztree_report(path) if path.is_dir() else path
    root = path.parent

    logger.info('File="{}"', path)
    if 'WizTree' not in path.name:
        logger.warning('대상이 WizTree 파일이 아닐 수 있음: "{}"', path)

    # 파일 불러오기
    works = read_wiztree_report(path)

    styler = HtmlStyler(viz=viz)
    console = rich.get_console()

    with pl.Config() as conf:
        conf.set_tbl_hide_column_data_types(False)
        conf.set_fmt_str_lengths(console.width // 2)

        console.print('Files by size:', style='blue bold')
        console.print(works.drop('size').head(10))

        styler.write_dfs(
            path=root / 'Works.html',
            df=works.drop('size'),
            subset=[Expr.MIB, 'files'],
        )

        # 그룹/작가별
        for by in ['group', 'author']:
            works_by = _by_group(works, by=by, drop_na=drop_na).drop('size')
            console.print('\nAuthors by size:', style='blue bold')
            console.print(works_by.head(10))

            styler.write_dfs(
                path=root / f'Works-{by.title()}.html',
                df=works_by,
                subset=[Expr.MIB, 'works', 'files'],
            )
