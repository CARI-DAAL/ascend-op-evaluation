# Deprecated Python import compatibility

Install alongside ascend-op-eval for existing Python callers that still import
`triton_evaluation`. The bridge aliases modules to canonical ascend_op_eval
objects, including old service/runtime module paths. This preserves class and
exception identity rather than loading a second implementation.

The bridge performs no historical-record conversion and adds no new wire
protocol. Migrate callers to canonical imports; remove the optional bridge only
when its consumers and retention obligations have been checked.
