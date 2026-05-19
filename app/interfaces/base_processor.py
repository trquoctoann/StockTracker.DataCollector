from abc import ABC, abstractmethod
from typing import Any


class BaseProcessor(ABC):
    @abstractmethod
    def process(self, raw: object, **kwargs: Any) -> object:
        pass
