"""Compatibility wrapper for the installed Ascend Op Eval entrypoint."""
from ascend_op_eval.entrypoints.run_api import app, build_app, main  # noqa: F401

if __name__ == "__main__":
    main()
