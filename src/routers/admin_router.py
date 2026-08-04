from fastapi import APIRouter, Depends, Request

from src.schemas.dtos.request_models.upload_files_request import UploadRequestModel
from src.services.process_service import ProcessFileService
from src.utilities.dependancies import get_process_service

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/upload-documents")
async def upload_documents(
    request: Request,
    body: UploadRequestModel,
    process_service: ProcessFileService = Depends(get_process_service),
):
    # try:
        # print("\nTHIS DATA IS COMING FROM USER", body, "\n\n", flush=True)
        response = await process_service.upload_file_s3(body)
        return response
    # except Exception as e:
    #     print(e)
