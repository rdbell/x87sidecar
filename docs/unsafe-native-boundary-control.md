# Unsafe native boundary control

Do not ship or merge this diagnostic branch into development.

This snapshot preserves the local control used to investigate the cost of
native x87 boundary conversion. The unconditional early return in
`emit_native_state_boundary` disables conversion in both directions. This
removes the PR #32 correctness behavior and can produce incorrect native x87
state, wrong results, or crashes.

This is an intentionally invalid correctness baseline for an isolated cost
comparison. It is not a performance fix. The production optimization remains
on `development` and retains the conversions.

Publication validation consists of reviewing the exact two-line source diff
and checking whitespace. No build, conformance suite, or game run was performed
for this archival commit. Existing benchmark artifacts and rollback binaries
remain local and are not included here. The installed runtime is unchanged.
