"""Tests for HeartbeatRunner."""

from unittest.mock import MagicMock, patch

from memento.heartbeat import HeartbeatRunner


def test_skips_when_stack_empty():
    mock_client = MagicMock()
    mock_client.kg.get_stack_status.return_value = {"message_count": 0}
    mock_client.config.agent_id = "test-agent"

    with patch("memento.bonfires_client.get_client", return_value=mock_client):
        runner = HeartbeatRunner(agent_id="test-agent")
        result = runner.run()
        assert result["skipped"] is True
        assert result["reason"] == "stack_empty"


def test_skips_when_already_processing():
    mock_client = MagicMock()
    mock_client.kg.get_stack_status.return_value = {"message_count": 5}
    mock_client.kg.process_stack.return_value = {"already_processing": True}
    mock_client.config.agent_id = "test-agent"

    with patch("memento.bonfires_client.get_client", return_value=mock_client):
        runner = HeartbeatRunner(agent_id="test-agent")
        result = runner.run()
        assert result["skipped"] is True
        assert result["reason"] == "already_processing"


def test_processes_and_returns_summary():
    mock_client = MagicMock()
    mock_client.kg.get_stack_status.return_value = {"message_count": 3}
    mock_client.kg.process_stack.return_value = {"task_id": "task-123"}
    mock_client.kg.wait_for_job.return_value = {"status": "completed"}
    mock_client.kg.get_latest_episode.return_value = {
        "uuid": "ep-456",
        "content": "A battle erupted in the tavern.",
        "entities": [],
        "edges": [],
    }
    mock_client.config.agent_id = "test-agent"
    mock_client.agents.get.return_value = {"name": "Narrator: The Threshold"}

    env_patch = {
        "MATRIX_AS_TOKEN": "test-token",
        "MATRIX_HOMESERVER": "http://localhost:8008",
        "MATRIX_DOMAIN": "localhost",
        "MEMENTO_GATEWAY_URL": "http://localhost:8080",
    }
    with patch("memento.bonfires_client.get_client", return_value=mock_client), \
         patch("memento.heartbeat._requests") as mock_requests, \
         patch.dict("os.environ", env_patch):
        # Mock the Matrix trigger (PUT to homeserver) and room lookup (GET)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_requests.put.return_value = mock_resp
        mock_requests.get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value={"room_id": "!test:localhost"})
        )

        runner = HeartbeatRunner(agent_id="test-agent")
        result = runner.run()
        assert result["processed"] is True
        assert result["episode_uuid"] == "ep-456"
        assert result["triggered"] is True


def test_handles_job_timeout():
    mock_client = MagicMock()
    mock_client.kg.get_stack_status.return_value = {"message_count": 3}
    mock_client.kg.process_stack.return_value = {"task_id": "task-123"}
    mock_client.kg.wait_for_job.return_value = {"status": "timeout"}
    mock_client.config.agent_id = "test-agent"

    with patch("memento.bonfires_client.get_client", return_value=mock_client):
        runner = HeartbeatRunner(agent_id="test-agent")
        result = runner.run()
        assert result["error"] == "job_timeout"


def test_handles_processing_exception():
    runner = HeartbeatRunner(agent_id="test-agent")
    # No mock — get_client will fail
    result = runner.run()
    assert "error" in result or "skipped" in result
