"""Tests for tactical response rendering."""

import io
import re
from contextlib import redirect_stdout

import pytest


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class TestResponseParsing:
    @pytest.mark.unit
    def test_parse_detects_markdown_blocks(self):
        from miliciano_ui import _parse_response_blocks

        text = """# Titulo

- item uno
- item dos

> nota

---

```python
print("hola")
```"""

        blocks = _parse_response_blocks(text)

        assert [block["type"] for block in blocks] == [
            "heading",
            "list",
            "quote",
            "rule",
            "code",
        ]
        assert blocks[0]["level"] == 1
        assert blocks[1]["items"][0]["text_lines"] == ["item uno"]
        assert blocks[4]["lines"] == ['print("hola")']

    @pytest.mark.unit
    def test_parse_plain_text_remains_paragraph(self):
        from miliciano_ui import _parse_response_blocks

        blocks = _parse_response_blocks("Linea uno\nLinea dos")

        assert blocks == [{"type": "paragraph", "text": "Linea uno Linea dos"}]


class TestResponseRendering:
    @pytest.mark.unit
    def test_render_list_wrap_keeps_hanging_indent(self):
        from miliciano_ui import _render_response_blocks

        blocks = [
            {
                "type": "list",
                "items": [
                    {
                        "marker": "-",
                        "text_lines": [
                            "este item es suficientemente largo para envolver en varias lineas sin perder sangria",
                        ],
                    }
                ],
            }
        ]

        lines = _render_response_blocks(blocks, width=44, compact=False, tactical=False)

        assert lines[0].startswith("• ")
        assert any(line.startswith("  ") for line in lines[1:])

    @pytest.mark.unit
    def test_render_code_preserves_internal_lines(self):
        from miliciano_ui import _render_response_blocks

        blocks = [{"type": "code", "lines": ["if x:", "    return y"], "info": "python"}]

        lines = _render_response_blocks(blocks, width=60, compact=False, tactical=False)

        assert any("if x:" in line for line in lines)
        assert any("    return y" in line for line in lines)

    @pytest.mark.unit
    def test_response_box_plain_text_keeps_content(self, monkeypatch):
        from miliciano_ui import response_box

        monkeypatch.setattr("miliciano_ui.terminal_width", lambda default=94: 50)
        monkeypatch.setattr("miliciano_ui.is_compact", lambda: False)
        monkeypatch.setattr("miliciano_ui.response_style", lambda: "tactical_markdown")

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            response_box("texto simple sin markdown", title="Test")

        output = buffer.getvalue()

        assert "texto simple sin markdown" in output
        assert "Test" in output

    @pytest.mark.unit
    def test_response_box_compact_keeps_basic_hierarchy(self, monkeypatch):
        from miliciano_ui import response_box

        monkeypatch.setattr("miliciano_ui.terminal_width", lambda default=94: 48)
        monkeypatch.setattr("miliciano_ui.is_compact", lambda: True)
        monkeypatch.setattr("miliciano_ui.response_style", lambda: "tactical_markdown")

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            response_box("## Plan\n\n1. paso largo para validar jerarquia", title="Plan")

        output = ANSI_RE.sub("", buffer.getvalue())

        assert "== Plan ==" in output
        assert "## Plan" in output
        assert "1. paso largo" in output

    @pytest.mark.unit
    def test_response_box_ansi_falls_back_without_breaking(self, monkeypatch):
        from miliciano_ui import response_box

        monkeypatch.setattr("miliciano_ui.terminal_width", lambda default=94: 60)
        monkeypatch.setattr("miliciano_ui.is_compact", lambda: False)
        monkeypatch.setattr("miliciano_ui.response_style", lambda: "tactical_markdown")

        colored = "\033[31mERROR\033[0m en rojo"
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            response_box(colored, title="ANSI")

        output = buffer.getvalue()

        assert colored in output

    @pytest.mark.unit
    def test_response_box_empty_text_does_not_deform(self, monkeypatch):
        from miliciano_ui import response_box

        monkeypatch.setattr("miliciano_ui.terminal_width", lambda default=94: 50)
        monkeypatch.setattr("miliciano_ui.is_compact", lambda: False)
        monkeypatch.setattr("miliciano_ui.response_style", lambda: "tactical_markdown")

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            response_box("", title="Vacio")

        output = buffer.getvalue()

        assert "Vacio" in output
        assert output.count("\n") >= 2
