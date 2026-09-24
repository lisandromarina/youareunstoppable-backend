from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.auth import router as auth_router
from src.services.auth import AuthError

app = FastAPI()
app.include_router(auth_router)


@app.exception_handler(AuthError)
def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/api/hello")
def hello():
    return {"message": "Hello from YouAreUnstoppable!"}
