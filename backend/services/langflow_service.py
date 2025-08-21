"""
Langflow service for handling API communication with Langflow instance.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class FlowResponse(BaseModel):
    """Response model for Langflow flow data."""
    id: str
    name: str
    folder_id: str
    is_component: bool
    endpoint_name: Optional[str] = None
    description: str
    data: Optional[Any] = None
    access_type: str
    tags: List[str]
    mcp_enabled: bool
    action_name: Optional[str] = None
    action_description: Optional[str] = None


class FlowExecutionRequest(BaseModel):
    """Request model for flow execution."""
    input_value: str
    output_type: str = "chat"
    input_type: str = "chat"
    tweaks: Dict[str, Any] = {}


class FlowExecutionResponse(BaseModel):
    """Response model for flow execution."""
    success: bool
    result: Any
    error: Optional[str] = None


class LangflowServiceError(Exception):
    """Custom exception for Langflow service errors."""
    pass


class LangflowService:
    """Service class for interacting with Langflow API."""
    
    def __init__(self, base_url: str = "http://localhost:7860", timeout: float = 30.0):
        """
        Initialize the Langflow service.
        
        Args:
            base_url: Base URL of the Langflow instance
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with proper configuration."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def _make_request_with_retry(
        self, 
        method: str, 
        url: str, 
        max_retries: int = 3,
        **kwargs
    ) -> httpx.Response:
        """
        Make HTTP request with retry logic.
        
        Args:
            method: HTTP method
            url: Request URL
            max_retries: Maximum number of retry attempts
            **kwargs: Additional arguments for the request
            
        Returns:
            HTTP response
            
        Raises:
            LangflowServiceError: If all retry attempts fail
        """
        client = await self._get_client()
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
                
            except httpx.TimeoutException as e:
                last_exception = e
                logger.warning(f"Request timeout on attempt {attempt + 1}/{max_retries + 1}: {url}")
                
            except httpx.ConnectError as e:
                last_exception = e
                logger.warning(f"Connection error on attempt {attempt + 1}/{max_retries + 1}: {url}")
                
            except httpx.HTTPStatusError as e:
                # Don't retry on client errors (4xx)
                if 400 <= e.response.status_code < 500:
                    raise LangflowServiceError(f"Client error {e.response.status_code}: {e.response.text}")
                last_exception = e
                logger.warning(f"HTTP error {e.response.status_code} on attempt {attempt + 1}/{max_retries + 1}: {url}")
            
            # Wait before retry (exponential backoff)
            if attempt < max_retries:
                wait_time = 2 ** attempt
                logger.info(f"Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
        
        # All retries failed
        error_msg = f"Failed to make request after {max_retries + 1} attempts: {last_exception}"
        logger.error(error_msg)
        raise LangflowServiceError(error_msg)
        
    async def get_flows(self) -> List[FlowResponse]:
        """
        Fetch all flows from Langflow API.
        
        Returns:
            List of flow responses
            
        Raises:
            LangflowServiceError: If the request fails or response is invalid
        """
        try:
            url = urljoin(self.base_url, "/api/v1/flows/")
            params = {
                "header_flows": "true",
                "get_all": "true"
            }
            
            logger.info(f"Fetching flows from Langflow: {url}")
            response = await self._make_request_with_retry("GET", url, params=params)
            
            # Parse response
            response_data = response.json()
            
            # Handle different response formats
            if isinstance(response_data, dict) and "flows" in response_data:
                flows_data = response_data["flows"]
            elif isinstance(response_data, list):
                flows_data = response_data
            else:
                raise LangflowServiceError(f"Unexpected response format: {type(response_data)}")
            
            # Validate and convert to FlowResponse objects
            flows = []
            for flow_data in flows_data:
                try:
                    flow = FlowResponse(**flow_data)
                    flows.append(flow)
                except ValidationError as e:
                    logger.warning(f"Failed to parse flow data: {e}")
                    continue
            
            logger.info(f"Successfully fetched {len(flows)} flows")
            return flows
            
        except Exception as e:
            if isinstance(e, LangflowServiceError):
                raise
            error_msg = f"Failed to fetch flows: {str(e)}"
            logger.error(error_msg)
            raise LangflowServiceError(error_msg)
    
    async def execute_flow(
        self, 
        flow_id: str, 
        execution_request: FlowExecutionRequest
    ) -> FlowExecutionResponse:
        """
        Execute a specific flow with given parameters.
        
        Args:
            flow_id: ID of the flow to execute
            execution_request: Execution parameters
            
        Returns:
            Flow execution response
            
        Raises:
            LangflowServiceError: If the execution fails
        """
        try:
            url = urljoin(self.base_url, f"/api/v1/run/{flow_id}")
            
            # Prepare request payload
            payload = execution_request.model_dump()
            
            logger.info(f"Executing flow {flow_id} with input: {execution_request.input_value[:100]}...")
            
            response = await self._make_request_with_retry(
                "POST", 
                url, 
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            response_data = response.json()
            
            # Create successful response
            execution_response = FlowExecutionResponse(
                success=True,
                result=response_data,
                error=None
            )
            
            logger.info(f"Successfully executed flow {flow_id}")
            return execution_response
            
        except LangflowServiceError as e:
            # Return error response instead of raising
            logger.error(f"Flow execution failed: {str(e)}")
            return FlowExecutionResponse(
                success=False,
                result=None,
                error=str(e)
            )
        except Exception as e:
            error_msg = f"Unexpected error during flow execution: {str(e)}"
            logger.error(error_msg)
            return FlowExecutionResponse(
                success=False,
                result=None,
                error=error_msg
            )
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()