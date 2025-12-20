from contextvars import ContextVar
from typing import Optional

# Request-scoped context variables
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
ip_address_var: ContextVar[Optional[str]] = ContextVar("ip_address", default=None)
user_agent_var: ContextVar[Optional[str]] = ContextVar("user_agent", default=None)
actor_id_var: ContextVar[Optional[str]] = ContextVar("actor_id", default=None)
account_id_var: ContextVar[Optional[UUID]] = ContextVar("account_id", default=None)
opt_in_debug_var: ContextVar[bool] = ContextVar("opt_in_debug", default=False)
