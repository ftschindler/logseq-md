"""Graphs and their config (DESIGN.md sections 4 and 8), and the narrow EDN reader."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from logseq_md import edn, names
from logseq_md.exits import BAD_ARGUMENTS, UNREADABLE, Refusal
from logseq_md.graph import ENVIRONMENT, open_graph, read_config

GRAPHS = Path(__file__).resolve().parent / "fixtures" / "graphs"


class TestOpen:
    def test_the_flag_wins_over_the_environment(self) -> None:
        flag, env = GRAPHS / "legacy", GRAPHS / "triple-lowbar"
        assert open_graph(str(flag), {ENVIRONMENT: str(env)}).root == flag

    def test_the_environment_is_used_without_the_flag(self) -> None:
        env = GRAPHS / "triple-lowbar"
        assert open_graph(None, {ENVIRONMENT: str(env)}).root == env

    def test_no_graph_named_is_bad_arguments(self) -> None:
        with pytest.raises(Refusal) as refused:
            open_graph(None, {})
        assert refused.value.code == BAD_ARGUMENTS

    def test_a_path_without_pages_or_journals_is_not_a_graph(self, tmp_path: Path) -> None:
        (tmp_path / "logseq").mkdir()
        with pytest.raises(Refusal) as refused:
            open_graph(str(tmp_path), {})
        assert refused.value.code == UNREADABLE
        assert str(tmp_path) in refused.value.message

    def test_a_missing_path_is_not_a_graph(self, tmp_path: Path) -> None:
        with pytest.raises(Refusal) as refused:
            open_graph(str(tmp_path / "nowhere"), {})
        assert refused.value.code == UNREADABLE

    def test_only_pages_and_journals_are_enumerated(self) -> None:
        root = GRAPHS / "skipped"
        files = [path.relative_to(root).as_posix() for path in open_graph(str(root), {}).files()]
        assert files == ["pages/kept.md"]


class TestConfig:
    def test_triple_lowbar(self) -> None:
        config = read_config(GRAPHS / "triple-lowbar")
        assert (config.name_format, config.notes) == (names.TRIPLE_LOWBAR, ())
        assert config.journal_file.pattern == names.DEFAULT_JOURNAL_FILE_FORMAT
        assert config.journal_title.pattern == names.DEFAULT_JOURNAL_TITLE_FORMAT

    def test_a_readable_config_without_the_key_is_legacy(self) -> None:
        config = read_config(GRAPHS / "legacy")
        assert (config.name_format, config.notes) == (names.LEGACY, ())

    def test_comments_strings_nesting_and_discards_are_not_settings(self) -> None:
        config = read_config(GRAPHS / "awkward-config")
        assert config.notes == ()
        assert config.name_format == names.TRIPLE_LOWBAR
        assert config.journal_file.pattern == "yyyy-MM-dd"
        assert config.journal_title.pattern == "EEEE, MMMM do 'of' yyyy"

    def test_an_unreadable_config_falls_back_and_says_so(self) -> None:
        root = GRAPHS / "unreadable-config"
        stderr = io.StringIO()
        graph = open_graph(str(root), {}, stderr)
        assert graph.config.name_format == names.TRIPLE_LOWBAR
        assert "cannot be read" in stderr.getvalue()
        assert "using Logseq's defaults" in stderr.getvalue()

    def test_a_missing_config_falls_back_and_says_so(self, tmp_path: Path) -> None:
        (tmp_path / "pages").mkdir()
        config = read_config(tmp_path)
        assert config.name_format == names.TRIPLE_LOWBAR
        assert len(config.notes) == 1

    def test_an_unknown_journal_token_falls_back_for_that_setting(self, tmp_path: Path) -> None:
        (tmp_path / "logseq").mkdir()
        (tmp_path / "logseq" / "config.edn").write_bytes(b'{:journal/file-name-format "yyyy-QQ"}')
        config = read_config(tmp_path)
        assert config.journal_file.pattern == names.DEFAULT_JOURNAL_FILE_FORMAT
        assert config.name_format == names.LEGACY
        assert len(config.notes) == 1


class TestEdn:
    @pytest.mark.parametrize(
        "text",
        [
            "[:file/name-format :legacy]",
            '{:file/name-format :legacy :x #inst "2024"}',
            '{:a #"regex"}',
            "{:file/name-format}",
            "{:file/name-format :legacy",
            '{:a "unterminated}',
            "{:a [1 2)}",
            "{:file/name-format [:legacy]}",
            "{:file/name-format legacy}",
            "{} {}",
        ],
    )
    def test_refuses_what_it_does_not_understand(self, text: str) -> None:
        with pytest.raises(edn.Unreadable):
            edn.read_config(text)

    def test_reads_keywords_and_unescaped_strings(self) -> None:
        text = '{:file/name-format :triple-lowbar, :journal/page-title-format "d\\"o"}'
        assert edn.read_config(text) == {":file/name-format": ":triple-lowbar", ":journal/page-title-format": 'd"o'}

    def test_a_nested_key_is_not_a_top_level_one(self) -> None:
        assert edn.read_config("{:a {:file/name-format :legacy} :b #{1 2} :c (x y)}") == {}
