from abc import ABC, abstractmethod
from typing import Any


class BaseSource(ABC):
    @abstractmethod
    async def extract(self, **kwargs: Any) -> Any:
        pass
