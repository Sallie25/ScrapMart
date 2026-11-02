"""Closed diagnostic vocabulary: never serialize exceptions, SQL or parameters."""
import json
import re

OPERATIONS = frozenset(('connection', 'transaction-setup', 'target', 'preconditions',
    'state-locks', 'role-state', 'role-create-settings', 'create-role', 'role-comment',
    'initial-audit', 'schema-checks', 'grant-database', 'grant-schema', 'grant-columns',
    'grant-delete', 'role-search-path', 'final-audit', 'commit', 'connection-close'))
CATEGORIES = frozenset(('permission-denied', 'authentication', 'connection', 'timeout',
    'transaction-conflict', 'postgresql-error', 'precondition-rejected', 'internal-error'))
PREFIX = 'D4_DIAGNOSTIC '


def failure(error, operation, commit_uncertain):
    from app.operations.runtime_role import RuntimeRoleRejected
    from app.operations.staging_bootstrap import BootstrapRejected
    original = getattr(error, 'orig', error)
    state = getattr(original, 'sqlstate', None)
    if not isinstance(state, str) or re.fullmatch(r'[0-9A-Z]{5}', state) is None:
        state = None
    category = 'internal-error'
    if isinstance(error, (RuntimeRoleRejected, BootstrapRejected)):
        category = 'precondition-rejected'
    if state:
        category = ('permission-denied' if state == '42501' else
                    'authentication' if state.startswith('28') else
                    'connection' if state.startswith('08') else
                    'timeout' if state in ('57014', '55P03') else
                    'transaction-conflict' if state.startswith('40') else 'postgresql-error')
    return dict(operation=operation if operation in OPERATIONS else 'connection',
                sqlstate=state, category=category, commit_uncertain=bool(commit_uncertain))


def render(record):
    return PREFIX + json.dumps(record, sort_keys=True)


def validated_child_report(output):
    """Accept exactly one closed-schema record; discard all other child output."""
    if not isinstance(output, str) or len(output) > 1024 or not output.startswith(PREFIX):
        return None
    try:
        record = json.loads(output[len(PREFIX):])
        if set(record) != {'operation', 'sqlstate', 'category', 'commit_uncertain'}:
            return None
        if record['operation'] not in OPERATIONS or record['category'] not in CATEGORIES:
            return None
        state = record['sqlstate']
        if state is not None and (not isinstance(state, str) or re.fullmatch(r'[0-9A-Z]{5}', state) is None):
            return None
        if type(record['commit_uncertain']) is not bool:
            return None
        return render(record)
    except (ValueError, TypeError):
        return None
