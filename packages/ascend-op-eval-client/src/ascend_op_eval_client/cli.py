"""Submit operators or immutable custom methods to Ascend Op Eval."""

import argparse
import sys

from . import __version__, methods


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--version"]:
        print(__version__)
        return 0
    if not arguments or arguments[0] in {"-h", "--help"}:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("command", choices=(
            "verify", "benchmark", "profile", "evaluate", "get", "progress", "version",
            "methods", "capabilities",
        ))
        parser.print_help()
        return 0
    if arguments[0] == "methods":
        return methods.main(arguments[1:])
    if arguments[0] == "capabilities":
        return methods.main(["runtimes", *arguments[1:]])
    # Task-format handling belongs to the independently installed default adapter.
    try:
        from ascend_op_eval_adapter_default.client import main as evaluate
    except ImportError:
        print("Install ascend-op-eval-adapter-default to use operator commands.", file=sys.stderr)
        return 2
    return evaluate(arguments)


if __name__ == "__main__":
    sys.exit(main())
