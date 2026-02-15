#!/usr/bin/env python3
"""
Rimal CLI (v0.1)

Commands:
  rml build file.rml   -> writes file.wat and file.wasm
  rml run   file.rml   -> compiles and executes, printing output
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

import wasmtime

from rimal.lexer import Lexer
from rimal.parser import Parser
from rimal.typechecker import TypeChecker
from rimal.wasm_compiler import WasmCompiler

_ARABIC_INDIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def _to_arabic_indic_i32(n: int) -> str:
    s = str(int(n))
    if s.startswith("-"):
        return "-" + s[1:].translate(_ARABIC_INDIC_DIGITS)
    return s.translate(_ARABIC_INDIC_DIGITS)


@dataclass(frozen=True)
class CliError(Exception):
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return self.message


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise CliError(f"File not found: {path}")

def _vlog(enabled: bool, msg: str) -> None:
    if enabled:
        print(f"[rml] {msg}", file=sys.stderr)


def compile_source(source: str, filename: str = "<input>", verbose: bool = False) -> tuple[str, bytes]:
    _vlog(verbose, "Lexing")
    tokens = Lexer(source, filename=filename).tokenize()
    _vlog(verbose, "Parsing")
    ast = Parser(tokens, filename=filename, source=source).parse_program()
    _vlog(verbose, "Type checking")
    tc = TypeChecker(ast, filename=filename, source=source)
    tc.check()
    _vlog(verbose, "Compiling to WAT/WASM")
    compiler = WasmCompiler()
    wat, wasm = compiler.compile(ast, print_types=tc.print_types)
    return wat, wasm


def write_build_outputs(input_path: str, wat: str, wasm: bytes) -> tuple[str, str]:
    base, _ = os.path.splitext(input_path)
    wat_path = base + ".wat"
    wasm_path = base + ".wasm"
    with open(wat_path, "w", encoding="utf-8") as f:
        f.write(wat)
    with open(wasm_path, "wb") as f:
        f.write(wasm)
    return wat_path, wasm_path


def run_wasm(wasm: bytes, verbose: bool = False) -> None:
    engine = wasmtime.Engine()
    store = wasmtime.Store(engine)

    _vlog(verbose, "Instantiating module")
    module = wasmtime.Module(engine, wasm)

    # Host functions
    def host_print_i32(val: int) -> None:
        print(_to_arabic_indic_i32(int(val)))

    def host_print_str(ptr: int, length: int) -> None:
        mem = instance.exports(store)["memory"]
        assert isinstance(mem, wasmtime.Memory)
        data = mem.read(store, ptr, ptr + length)
        s = bytes(data).decode("utf-8", errors="replace")
        print(s)

    linker = wasmtime.Linker(engine)
    linker.define(
        store,
        "host",
        "print_i32",
        wasmtime.Func(store, wasmtime.FuncType([wasmtime.ValType.i32()], []), host_print_i32),
    )
    linker.define(
        store,
        "host",
        "print_str",
        wasmtime.Func(
            store,
            wasmtime.FuncType([wasmtime.ValType.i32(), wasmtime.ValType.i32()], []),
            host_print_str,
        ),
    )

    instance = linker.instantiate(store, module)
    run_fn = instance.exports(store)["run"]
    if not isinstance(run_fn, wasmtime.Func):
        raise CliError("Internal error: exported 'run' is not a function")
    _vlog(verbose, "Executing run()")
    run_fn(store)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    parser = argparse.ArgumentParser(prog="rml", description="Rimal compiler (v0.1)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="Compile .rml to .wat and .wasm")
    p_build.add_argument("file", help="Path to .rml source file")
    p_build.add_argument("-v", "--verbose", action="store_true", help="Print internal compilation steps to stderr")

    p_run = sub.add_parser("run", help="Compile and execute via Wasmtime")
    p_run.add_argument("file", help="Path to .rml source file")
    p_run.add_argument("-v", "--verbose", action="store_true", help="Print internal compilation steps to stderr")

    args = parser.parse_args(argv)

    try:
        src = _read_text(args.file)
        wat, wasm = compile_source(src, filename=args.file, verbose=bool(getattr(args, "verbose", False)))

        if args.cmd == "build":
            _vlog(bool(getattr(args, "verbose", False)), "Writing outputs")
            wat_path, wasm_path = write_build_outputs(args.file, wat, wasm)
            print(wat_path)
            print(wasm_path)
            return 0

        if args.cmd == "run":
            run_wasm(wasm, verbose=bool(getattr(args, "verbose", False)))
            return 0

        raise CliError(f"Unknown command: {args.cmd}")
    except CliError as e:
        print(str(e), file=sys.stderr)
        return 2
    except Exception as e:
        # Surface compiler errors cleanly.
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

