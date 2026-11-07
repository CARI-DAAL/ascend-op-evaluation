# Implementation plans

- [Ascend Op Eval spec and AOE tickets](ascend-op-eval/README.md): proposed generic
  execution/resource/adapter work. Ticket files own status and acceptance;
  graph.json indexes dependencies only.
- [Version identity tickets](version-system-tickets.json): retain their original
  identities and implementation evidence; assess remaining scope against code.
- [Evaluation efficiency tickets](evaluation-efficiency-tickets.json): a distinct
  workstream, not a second copy of the AOE tracker.
- [Benchmark pipe-utilization handoff](benchmark-pipe-utilization.md): targeted
  server-side evidence collection.

Custom-method-v1 has now been implemented on the existing evaluation lifecycle;
see the [current method guide](../guides/custom-methods.md). Its historical
implementation prompt is retained in the AOE plan directory for provenance, not
as a declaration that this functionality is still absent. Generic executions,
child isolation and multi-card scheduling remain separate planned work.
