import os


def env(name: str, default: str) -> str:
    return os.getenv(name, default)


DATABASE_URL = env("DATABASE_URL", "postgresql+psycopg://cloud:cloud@localhost:5432/cloud_g03")
SERVICE_NAME = env("SERVICE_NAME", "grupo03-service")
