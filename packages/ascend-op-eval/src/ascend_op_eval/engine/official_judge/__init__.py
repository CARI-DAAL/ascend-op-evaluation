"""Local replication of the official cannbench.com correctness judge.

Vendored sources (preserve Huawei CANN OSL 2.0 headers): compare.py /
thresholds.py / tensor_utils.py extracted from the official eval image's
/opt/cann-bench/src/kernel_eval/utils/. judge.py drives them against a
candidate kernel + task spec to predict per-case official outcomes BEFORE
spending submission credits.
"""
