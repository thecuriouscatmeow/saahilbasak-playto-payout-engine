import json
import structlog
from observability.correlation import bind_correlation_id


def test_correlation_id_in_log(capsys):
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

    with bind_correlation_id("test-cid-123"):
        logger = structlog.get_logger()
        logger.info("test_event", key="value")

    captured = capsys.readouterr()
    # Find the line with our event
    for line in captured.out.splitlines():
        try:
            data = json.loads(line)
            if data.get("event") == "test_event":
                assert data["correlation_id"] == "test-cid-123"
                assert data["key"] == "value"
                return
        except json.JSONDecodeError:
            continue
    raise AssertionError("Log line with test_event not found in output")
