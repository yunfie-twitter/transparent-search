import asyncio
from arq.connections import RedisSettings
from .tasks import crawl_domain_task

async def startup(ctx):
    print("Worker starting...")

async def shutdown(ctx):
    print("Worker shutting down...")

class WorkerSettings:
    functions = [crawl_domain_task]
    redis_settings = RedisSettings(host='redis', port=6379)
    on_startup = startup
    on_shutdown = shutdown
