"""Authenticated polling APIs for Buyer–Vendor text conversations."""
import json
from typing import Annotated
from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from app.api.v1.buyer_account import access_claims, invalid_authentication
from app.api.v1.buyer_sessions import session_guard, SECURITY_PARAMETERS
from app.api.v1.buyer_signup import fail
from app.api.v1.marketplace import identifier, query_params, page
from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_engine
from app.infrastructure.storage.private_documents import VerificationInfrastructureUnavailable
from app.modules.auth.security import AccessTokenClaims, SecurityConfigurationError
from app.modules.auth.session_service import SessionAuthenticationError, SessionPersistenceError
from app.modules.auth.vendor_authorization import VendorPermissionError
from app.modules.messaging.schemas import StartConversation, SendMessage, ReadMessage
from app.modules.messaging.service import MessagingService, ConversationNotFound, MessagingConflict

router = APIRouter(prefix='/conversations', tags=['Messaging'])


def perform(settings, operation):
    try: return operation(MessagingService(get_engine(), settings=settings))
    except SessionAuthenticationError: invalid_authentication()
    except VendorPermissionError: fail(403, 'messaging_forbidden', 'Current approved Vendor evidence is required')
    except ConversationNotFound: fail(404, 'conversation_not_found', 'Conversation or message is not available')
    except MessagingConflict: fail(409, 'messaging_conflict', 'Conversation or request conflicts with current state')
    except (SessionPersistenceError, SecurityConfigurationError, SQLAlchemyError, OSError, VerificationInfrastructureUnavailable):
        fail(503, 'messaging_unavailable', 'Messaging is temporarily unavailable')


async def messaging_input(request: Request, _: Annotated[None, Depends(session_guard)]):
    model = SendMessage if request.url.path.endswith('/messages') else ReadMessage if request.url.path.endswith('/read') else StartConversation
    types = request.headers.getlist('content-type')
    if len(types) != 1 or types[0].split(';', 1)[0].strip().lower() != 'application/json':
        fail(415, 'unsupported_media_type', 'Use application/json')
    try: return model.model_validate(json.loads(await request.body()))
    except (ValidationError, ValueError, UnicodeError, RecursionError):
        fail(422, 'validation_error', 'Invalid messaging fields')


Claims = Annotated[AccessTokenClaims, Depends(access_claims)]
Config = Annotated[Settings, Depends(get_settings)]
Input = Annotated[StartConversation | SendMessage | ReadMessage, Depends(messaging_input)]


@router.post('', status_code=201, openapi_extra={'parameters': SECURITY_PARAMETERS})
def start(value: Input, claims: Claims, settings: Config):
    return perform(settings, lambda service: service.start(claims, value))


@router.get('')
def conversations(request: Request, claims: Claims, settings: Config):
    limit, cursor = page(query_params(request, {'limit', 'cursor'}), 50)
    return perform(settings, lambda service: service.run(claims, 'list', limit=limit, cursor=cursor))


@router.get('/unread')
def unread(claims: Claims, settings: Config):
    return perform(settings, lambda service: service.run(claims, 'unread'))


@router.get('/{conversation_id}/messages')
def history(conversation_id: str, request: Request, claims: Claims, settings: Config):
    key = identifier(conversation_id)
    limit, cursor = page(query_params(request, {'limit', 'cursor'}), 100)
    return perform(settings, lambda service: service.run(claims, 'history', key=key, limit=limit, cursor=cursor))


@router.post('/{conversation_id}/messages', status_code=201, openapi_extra={'parameters': SECURITY_PARAMETERS})
def send(conversation_id: str, value: Input, claims: Claims, settings: Config):
    key = identifier(conversation_id)
    return perform(settings, lambda service: service.run(claims, 'send', key=key, value=value))


@router.post('/{conversation_id}/read', openapi_extra={'parameters': SECURITY_PARAMETERS})
def read(conversation_id: str, value: Input, claims: Claims, settings: Config):
    key = identifier(conversation_id)
    return perform(settings, lambda service: service.run(claims, 'read', key=key, value=value))
