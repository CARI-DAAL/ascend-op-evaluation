"""Installed Ascend Op Eval process commands."""

import argparse
import sys


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("api", "worker"))
    args, remaining = parser.parse_known_args(argv)
    if args.command == "api":
        if remaining:
            parser.error("api uses ASCEND_OP_EVAL_* settings; unexpected arguments")
        from ascend_op_eval.entrypoints.run_api import main as run
    else:
        from ascend_op_eval.entrypoints.run_worker import main as run
    sys.argv = [sys.argv[0], *remaining]
    run()


if __name__ == "__main__":
    main()
