"""
Unit tests for LangflowService.
"""

import pytest
from unittest.mock import AsyncMock, patch
import httpx
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.langflow_service import (
    LangflowService,
    FlowExecutionRequest,
    FlowResponse,
    FlowExecutionResponse,
    LangflowServiceError,
)


class TestLangflowService:
    """Test cases for LangflowService."""

    @pytest.fixture
    def service(self):
        """Create a LangflowService instance for testing."""
        return LangflowService(base_url="http://test-langflow:7860", timeout=10.0)

    @pytest.fixture
    def mock_flows_response(self):
        """Mock response data for flows API."""
        return [
            {
                "id": "flow-1",
                "name": "Test Flow 1",
                "folder_id": "folder-1",
                "is_component": False,
                "endpoint_name": None,
                "description": "A test flow",
                "data": None,
                "access_type": "public",
                "tags": ["test", "demo"],
                "mcp_enabled": True,
                "action_name": None,
                "action_description": None,
            },
            {
                "id": "flow-2",
                "name": "Test Flow 2",
                "folder_id": "folder-1",
                "is_component": True,
                "endpoint_name": "test_endpoint",
                "description": "Another test flow",
                "data": {"some": "data"},
                "access_type": "private",
                "tags": ["test"],
                "mcp_enabled": False,
                "action_name": "test_action",
                "action_description": "Test action description",
            },
        ]

    @pytest.fixture
    def mock_execution_response(self):
        """Mock response data for flow execution."""
        return {
            "result": "Flow executed successfully",
            "output": "Test output",
            "session_id": "test-session-123",
        }

    @pytest.mark.asyncio
    async def test_get_flows_success(self, service, mock_flows_response):
        """Test successful flow retrieval."""
        with patch.object(service, "_make_request_with_retry") as mock_request:
            # Mock successful response
            mock_response = AsyncMock()
            mock_response.json = lambda: mock_flows_response
            mock_request.return_value = mock_response

            # Call the method
            flows = await service.get_flows()

            # Verify the request
            mock_request.assert_called_once_with(
                "GET",
                "http://test-langflow:7860/api/v1/flows/",
                params={"components_only": "true", "get_all": "true"},
            )

            # Verify the response
            assert len(flows) == 2
            assert isinstance(flows[0], FlowResponse)
            assert flows[0].id == "flow-1"
            assert flows[0].name == "Test Flow 1"
            assert flows[0].tags == ["test", "demo"]
            assert flows[1].id == "flow-2"
            assert flows[1].mcp_enabled is False

    @pytest.mark.asyncio
    async def test_get_flows_with_flows_wrapper(self, service, mock_flows_response):
        """Test flow retrieval when response is wrapped in 'flows' key."""
        with patch.object(service, "_make_request_with_retry") as mock_request:
            # Mock response with flows wrapper
            mock_response = AsyncMock()
            mock_response.json.return_value = {"flows": mock_flows_response}
            mock_request.return_value = mock_response

            flows = await service.get_flows()

            assert len(flows) == 2
            assert flows[0].id == "flow-1"

    @pytest.mark.asyncio
    async def test_get_flows_invalid_data(self, service):
        """Test flow retrieval with invalid flow data."""
        with patch.object(service, "_make_request_with_retry") as mock_request:
            # Mock response with invalid flow data
            invalid_flows = [
                {
                    "id": "flow-1",
                    "name": "Valid Flow",
                    "folder_id": "folder-1",
                    "is_component": False,
                    "description": "Valid flow",
                    "access_type": "public",
                    "tags": [],
                    "mcp_enabled": True,
                },
                {
                    "id": "flow-2",
                    # Missing required fields
                    "name": "Invalid Flow",
                },
            ]

            mock_response = AsyncMock()
            mock_response.json.return_value = invalid_flows
            mock_request.return_value = mock_response

            flows = await service.get_flows()

            # Should only return valid flows
            assert len(flows) == 1
            assert flows[0].id == "flow-1"

    @pytest.mark.asyncio
    async def test_get_flows_request_failure(self, service):
        """Test flow retrieval when request fails."""
        with patch.object(service, "_make_request_with_retry") as mock_request:
            mock_request.side_effect = LangflowServiceError("Connection failed")

            with pytest.raises(LangflowServiceError, match="Connection failed"):
                await service.get_flows()

    @pytest.mark.asyncio
    async def test_execute_flow_success(self, service, mock_execution_response):
        """Test successful flow execution."""
        with patch.object(service, "_make_request_with_retry") as mock_request:
            # Mock successful response
            mock_response = AsyncMock()
            mock_response.json.return_value = mock_execution_response
            mock_request.return_value = mock_response

            # Create execution request
            execution_request = FlowExecutionRequest(
                input_value="Test input",
                output_type="chat",
                input_type="chat",
                tweaks={"param1": "value1"},
            )

            # Execute flow
            result = await service.execute_flow("flow-1", execution_request)

            # Verify the request
            mock_request.assert_called_once_with(
                "POST",
                "http://test-langflow:7860/api/v1/run/flow-1",
                json={
                    "input_value": "Test input",
                    "output_type": "chat",
                    "input_type": "chat",
                    "tweaks": {"param1": "value1"},
                },
                headers={"Content-Type": "application/json"},
            )

            # Verify the response
            assert isinstance(result, FlowExecutionResponse)
            assert result.success is True
            assert result.result == mock_execution_response
            assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_flow_failure(self, service):
        """Test flow execution when request fails."""
        with patch.object(service, "_make_request_with_retry") as mock_request:
            mock_request.side_effect = LangflowServiceError("Execution failed")

            execution_request = FlowExecutionRequest(input_value="Test input")
            result = await service.execute_flow("flow-1", execution_request)

            # Should return error response instead of raising
            assert isinstance(result, FlowExecutionResponse)
            assert result.success is False
            assert result.result is None
            assert "Execution failed" in result.error

    @pytest.mark.asyncio
    async def test_make_request_with_retry_success(self, service):
        """Test successful request without retries."""
        with patch.object(service, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.raise_for_status.return_value = None
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await service._make_request_with_retry("GET", "http://test.com")

            assert result == mock_response
            mock_client.request.assert_called_once_with("GET", "http://test.com")

    @pytest.mark.asyncio
    async def test_make_request_with_retry_timeout_then_success(self, service):
        """Test request that fails with timeout then succeeds."""
        with patch.object(service, "_get_client") as mock_get_client:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_client = AsyncMock()
                mock_response = AsyncMock()
                mock_response.raise_for_status.return_value = None

                # First call raises timeout, second succeeds
                mock_client.request.side_effect = [
                    httpx.TimeoutException("Timeout"),
                    mock_response,
                ]
                mock_get_client.return_value = mock_client

                result = await service._make_request_with_retry(
                    "GET", "http://test.com"
                )

                assert result == mock_response
                assert mock_client.request.call_count == 2
                mock_sleep.assert_called_once_with(1)  # 2^0 = 1 second wait

    @pytest.mark.asyncio
    async def test_make_request_with_retry_max_retries_exceeded(self, service):
        """Test request that fails all retry attempts."""
        with patch.object(service, "_get_client") as mock_get_client:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                mock_client = AsyncMock()
                mock_client.request.side_effect = httpx.TimeoutException(
                    "Persistent timeout"
                )
                mock_get_client.return_value = mock_client

                with pytest.raises(
                    LangflowServiceError,
                    match="Failed to make request after 4 attempts",
                ):
                    await service._make_request_with_retry(
                        "GET", "http://test.com", max_retries=3
                    )

                assert mock_client.request.call_count == 4  # Initial + 3 retries

    @pytest.mark.asyncio
    async def test_make_request_with_retry_client_error_no_retry(self, service):
        """Test that client errors (4xx) are not retried."""
        with patch.object(service, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 400
            mock_response.text = "Bad Request"

            error = httpx.HTTPStatusError(
                "Bad Request", request=AsyncMock(), response=mock_response
            )
            mock_client.request.side_effect = error
            mock_get_client.return_value = mock_client

            with pytest.raises(LangflowServiceError, match="Client error 400"):
                await service._make_request_with_retry("GET", "http://test.com")

            # Should not retry on client errors
            assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_context_manager(self, service):
        """Test async context manager functionality."""
        with patch.object(service, "close") as mock_close:
            async with service as svc:
                assert svc == service

            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_client(self, service):
        """Test client cleanup."""
        # Create a mock client
        mock_client = AsyncMock()
        mock_client.is_closed = False
        service._client = mock_client

        await service.close()

        mock_client.aclose.assert_called_once()
