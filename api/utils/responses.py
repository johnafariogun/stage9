from typing import Optional

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def success_response(status_code: int, message: str, 
                     data: Optional[dict] = None):
    """Returns a JSON response for success responses"""

    response_data = {
        "status": "success",
        "status_code": status_code,
        "message": message,
        "data": data or {},
    }

    return JSONResponse(
        status_code=status_code, content=jsonable_encoder(response_data)
    )



def fail_response(status_code: int, message: str, 
                  context: Optional[dict] = None):
    """Returns a JSON response for failure responses"""

    response_data = {
        "status": "failure",
        "status_code": status_code,
        "message": message,
        "error": context or {},
    }

    return JSONResponse(
        status_code=status_code, content=jsonable_encoder(response_data)
    )

    
