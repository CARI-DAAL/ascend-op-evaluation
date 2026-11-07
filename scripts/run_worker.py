"""Compatibility wrapper for the installed Ascend Op Eval entrypoint."""
from ascend_op_eval.entrypoints.run_worker import (  # noqa: F401
    build_worker,
    hold_device,
    main,
    set_process_title,
)

if __name__ == "__main__":
    main()
