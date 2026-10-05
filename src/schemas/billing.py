from datetime import datetime

from pydantic import BaseModel


class BillingUrlResponse(BaseModel):
    url: str
