# tests/test_example_imports.py
import ast
import pathlib


def test_quickstart_is_valid_python_and_uses_public_api():
    src = pathlib.Path("examples/quickstart.py").read_text()
    ast.parse(src)  # raises SyntaxError if malformed
    assert "from social_media_automations import Bot" in src
    assert "run_polling()" in src
    assert "@app.on_message" in src
