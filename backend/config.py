from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    cerebras_api_key: str = Field(..., validation_alias="CEREBRAS_API_KEY")
    cesium_ion_token: str = Field(..., validation_alias="CESIUM_ION_TOKEN")
    tick_interval: float = 2.0
    grid_size: int = 10
    num_drones: int = 20
    cesium_asset_name: str = "Bing Maps Aerial"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()