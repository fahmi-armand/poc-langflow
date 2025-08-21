from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from services.langflow_service import (
    LangflowService,
    LangflowServiceError,
    FlowExecutionRequest,
)

app = FastAPI(title="Langflow Integration API", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExecuteFlowRequest(BaseModel):
    input_value: str
    tweaks: dict = {}


@app.get("/")
async def root():
    return {"message": "Langflow Integration API"}


@app.get("/flows")
async def get_flows():
    """Get all available flows from Langflow."""
    try:
        async with LangflowService() as service:
            flows = await service.get_flows()
            return {"flows": [flow.model_dump() for flow in flows]}
    except LangflowServiceError as e:
        raise HTTPException(status_code=503, detail=f"Langflow service error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.post("/flows/{flow_id}/execute")
async def execute_flow(flow_id: str, request: ExecuteFlowRequest):
    """Execute a specific flow."""
    try:
        async with LangflowService() as service:
            execution_request = FlowExecutionRequest(
                input_value=request.input_value, tweaks=request.tweaks
            )

            result = await service.execute_flow(flow_id, execution_request)
            return result.model_dump()
    except LangflowServiceError as e:
        raise HTTPException(status_code=503, detail=f"Langflow service error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.post("/test-flow")
async def test_hardcoded_flow(request: ExecuteFlowRequest):
    """Test endpoint with hardcoded flow ID de90b072-14d5-4983-b9ac-85156fef9bb4."""
    hardcoded_flow_id = "de90b072-14d5-4983-b9ac-85156fef9bb4"

    try:
        async with LangflowService() as service:
            execution_request = FlowExecutionRequest(
                input_value=request.input_value, tweaks=request.tweaks
            )

            result = await service.execute_flow(hardcoded_flow_id, execution_request)
            return {
                "flow_id": hardcoded_flow_id,
                "execution_result": result.model_dump(),
            }
    except LangflowServiceError as e:
        raise HTTPException(status_code=503, detail=f"Langflow service error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.get("/test-langflow")
async def test_langflow():
    """Test endpoint to verify Langflow service connectivity."""
    try:
        async with LangflowService() as service:
            flows = await service.get_flows()
            return {
                "status": "success",
                "message": f"Successfully connected to Langflow. Found {len(flows)} flows.",
                "flows_count": len(flows),
                "sample_flows": [
                    {"id": flow.id, "name": flow.name} for flow in flows[:3]
                ],
            }
    except LangflowServiceError as e:
        raise HTTPException(status_code=503, detail=f"Langflow service error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
