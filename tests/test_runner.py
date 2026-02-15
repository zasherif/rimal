from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_PROGRAMS = ROOT / "tests" / "test_programs"


@dataclass(frozen=True)
class TestCase:
    name: str
    path: Path
    expected_stdout: str | None  # None means expect failure
    expected_error_substr: str | None = None


def _compile_and_run(source_path: Path) -> str:
    # Import from project root module `rml.py`
    sys.path.insert(0, str(ROOT))
    try:
        import rml  # type: ignore

        src = source_path.read_text(encoding="utf-8")
        _wat, wasm = rml.compile_source(src, filename=str(source_path))

        buf = io.StringIO()
        with redirect_stdout(buf):
            rml.run_wasm(wasm)
        return buf.getvalue()
    finally:
        if sys.path and sys.path[0] == str(ROOT):
            sys.path.pop(0)


def run_tests() -> int:
    cases = [
        TestCase("Arithmetic", TEST_PROGRAMS / "arithmetic.rml", "١٤\n"),
        TestCase("If/Else", TEST_PROGRAMS / "if_else.rml", "١٠\n"),
        TestCase("While Loop", TEST_PROGRAMS / "while_loop.rml", "٠\n١\n٢\n"),
        TestCase("Comments", TEST_PROGRAMS / "comments.rml", "٠\n١\n٢\n"),
        TestCase("Boolean Ops", TEST_PROGRAMS / "boolean_ops.rml", "٠\n١\n١\n١\n"),
        TestCase("Elif Chain", TEST_PROGRAMS / "elif_chain.rml", "٢٠\n"),
        TestCase("Break/Continue", TEST_PROGRAMS / "break_continue.rml", "١\n٣\n"),
        TestCase("Multiline Expr", TEST_PROGRAMS / "multiline_expr.rml", "١٤\n"),
        TestCase("Nested Parens", TEST_PROGRAMS / "nested_parens.rml", "٤٨\n"),
        TestCase("Functions", TEST_PROGRAMS / "functions_basic.rml", "٥\n١٤\n"),
        TestCase("Strings", TEST_PROGRAMS / "strings.rml", "مرحبا\n"),
        TestCase(
            "Invalid Syntax",
            TEST_PROGRAMS / "invalid_syntax.rml",
            None,
            expected_error_substr="Expected ':' after if condition",
        ),
    ]

    passed = 0
    failed = 0

    for tc in cases:
        try:
            out = _compile_and_run(tc.path)
            if tc.expected_stdout is None:
                raise AssertionError("Expected failure but program ran successfully")
            if out != tc.expected_stdout:
                raise AssertionError(f"stdout mismatch\n--- expected ---\n{tc.expected_stdout!r}\n--- got ---\n{out!r}")
            print(f"[PASS] {tc.name}")
            passed += 1
        except Exception as e:
            if tc.expected_stdout is None:
                msg = str(e)
                if tc.expected_error_substr and tc.expected_error_substr not in msg:
                    print(f"[FAIL] {tc.name}: error mismatch")
                    print(f"  expected to contain: {tc.expected_error_substr!r}")
                    print(f"  got: {msg!r}")
                    failed += 1
                else:
                    print(f"[PASS] {tc.name}")
                    passed += 1
            else:
                print(f"[FAIL] {tc.name}: {e}")
                failed += 1

    print()
    print(f"Summary: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


def main() -> int:
    if not TEST_PROGRAMS.exists():
        print(f"Missing test programs directory: {TEST_PROGRAMS}", file=sys.stderr)
        return 2
    return run_tests()


if __name__ == "__main__":
    raise SystemExit(main())

