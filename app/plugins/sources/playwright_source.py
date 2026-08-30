from typing import Any

from app.interfaces.base_source import BaseSource


class PlaywrightSource(BaseSource):
    async def extract(self, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "PlaywrightSource is not implemented; add a scraping job in plugins/sources/playwright_source.py"
        )
