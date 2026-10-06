from pydantic import BaseModel


class BillingStatusResponse(BaseModel):
    enabled: bool


class BillingUrlResponse(BaseModel):
    url: str
