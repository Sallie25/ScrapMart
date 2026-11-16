"""Reservations are authoritative order quantities, not decremented listing fields.

All writers lock the Vendor User and Listing before counting/changing reservations.
Completed quantities remain consumed; only cancellation/rejection releases stock.
"""
from decimal import Decimal
from sqlalchemy import select,func
from app.modules.orders.models import Order,OrderItem

COUNTED_STATUSES=('pending','accepted','preparing','delivered','completed')


def reserved_quantity_expression():
    from app.modules.listings.models import Listing
    return select(func.coalesce(func.sum(OrderItem.quantity),0)).join(
        Order,Order.id==OrderItem.order_id).where(OrderItem.listing_id==Listing.id,
        Order.status.in_(COUNTED_STATUSES)).correlate(Listing).scalar_subquery()


def reserved_quantity(db,listing_id):
    value=db.scalar(select(func.coalesce(func.sum(OrderItem.quantity),0)).join(Order,Order.id==OrderItem.order_id).where(
        OrderItem.listing_id==listing_id,Order.status.in_(COUNTED_STATUSES)))
    return Decimal(value or 0)


def available_quantity(db,listing):
    return max(Decimal(0),Decimal(listing.quantity or 0)-reserved_quantity(db,listing.id))


def validate_inventory_edit(db,listing,values):
    from app.modules.listings.service import InvalidListing
    exists=db.scalar(select(OrderItem.id).where(OrderItem.listing_id==listing.id).limit(1))
    if exists is None: return
    if values.get('quantity_unit')!=listing.quantity_unit or values.get('price_type')!=listing.price_type:
        raise InvalidListing('Create a new listing to change ordered units or pricing basis')
    reserved=reserved_quantity(db,listing.id)
    if reserved and listing.price_type=='total' and values.get('quantity')!=listing.quantity:
        raise InvalidListing('A committed whole lot cannot change quantity')
    if reserved and (values.get('quantity') is None or values['quantity']<reserved):
        raise InvalidListing('Quantity cannot be below reserved or fulfilled orders')
