from solids.domain.states import ExecutionStatus, GeologicalState


def test_geological_states_are_exactly_four():
    assert [s.value for s in GeologicalState] == [
        "SIN CAMBIOS", "VARIABLE", "NUEVO", "ELIMINADO",
    ]


def test_execution_states_are_independent_of_geological_ones():
    assert [s.value for s in ExecutionStatus] == [
        "queued", "running", "completed", "completed_with_issues", "failed", "cancelled",
    ]
