"""No client price, Vendor, Buyer identity, status or payment fields are accepted."""
import uuid
from decimal import Decimal
from pydantic import BaseModel,ConfigDict,field_validator
from app.modules.listings.schemas import exact_decimal


class EmptyOrderRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)


class PlaceOrderRequest(EmptyOrderRequest):
    listing_id: uuid.UUID
    request_id: uuid.UUID
    quantity: Decimal

    @field_validator('listing_id','request_id',mode='before')
    @classmethod
    def uuid_valid(cls,value):
        if isinstance(value,uuid.UUID): return value
        try:
            result=uuid.UUID(value)
            if str(result)!=value: raise ValueError()
            return result
        except (ValueError,AttributeError,TypeError): raise ValueError('Invalid identifier') from None

    @field_validator('quantity',mode='before')
    @classmethod
    def quantity_valid(cls,value):
        result=exact_decimal(value,3,Decimal('100000000000'),positive=True)
        if result is None: raise ValueError('Quantity is required')
        return result
