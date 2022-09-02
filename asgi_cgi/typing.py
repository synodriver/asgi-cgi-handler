from typing import Any, Awaitable, Callable, Dict, MutableMapping, Union

Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
Receive = Callable[[], Awaitable[Dict[str, Any]]]
ErrHandler = Callable[[bytes], Union[Awaitable[None], None]]
