from app.agentops.reliability import CircuitBreaker, CircuitState


def test_circuit_breaker_opens_after_threshold():
    breaker = CircuitBreaker(failure_threshold=2, recovery_seconds=10)

    breaker.record_failure(now=1)
    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request(now=2) is True

    breaker.record_failure(now=3)
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request(now=4) is False


def test_circuit_breaker_moves_to_half_open_after_recovery():
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=10)
    breaker.record_failure(now=1)

    assert breaker.allow_request(now=12) is True
    assert breaker.state == CircuitState.HALF_OPEN


def test_circuit_breaker_success_closes_and_resets_failures():
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=10)
    breaker.record_failure(now=1)
    breaker.record_success()

    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0
    assert breaker.allow_request(now=2) is True
