from abc import ABC, abstractmethod
from collections.abc import Sequence

from pydantic import BaseModel


class BaseSink(ABC):
    @abstractmethod
    async def send_batch(self, entity: str, items: Sequence[BaseModel]) -> None:
        pass

    async def close(self) -> None:
        return
