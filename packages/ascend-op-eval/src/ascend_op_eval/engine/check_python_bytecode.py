"""Compile the submitted Python candidate module without importing or executing it."""

import json
import sys
from pathlib import Path


def main():
    source = Path(sys.argv[1]).read_text(encoding="utf-8")
    try:
        compile(source, "<candidate>", "exec", dont_inherit=True)
    except SyntaxError as exc:
        location = f"line {exc.lineno}, column {exc.offset}" if exc.offset else f"line {exc.lineno}"
        message = f"{type(exc).__name__} ({location}): {exc.msg}"
        error = message.encode("utf-8")[:400].decode("utf-8", errors="ignore")
    except ValueError as exc:
        # Older CPython versions report embedded null bytes as ValueError.
        error = str(exc)
    else:
        error = None
    print("VERDICT " + json.dumps({
        "compile_mode": "python_bytecode",
        "compiler_stage": "frontend",
        "outcome": "compiled" if error is None else "compile_error",
        "error_excerpt": error,
    }))


if __name__ == "__main__":
    main()
