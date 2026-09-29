from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.admin import router as admin_router
from src.api.auth import router as auth_router
from src.api.transformation import router as transformation_router
from src.services.auth import AuthError
from src.services.errors import DomainError

app = FastAPI()
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(transformation_router)


@app.exception_handler(AuthError)
def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(DomainError)
def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/api/hello")
def hello():
    return {"message": "Hello from YouAreUnstoppable!"}
