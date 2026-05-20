from typing import Any

from app.interfaces.base_source import BaseSource


class PlaywrightSource(BaseSource):
    async def extract(self, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "PlaywrightSource chưa triển khai: thêm job scraping trong plugins/sources/playwright_source.py"
        )
