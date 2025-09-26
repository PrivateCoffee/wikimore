from flask_caching import Cache
import os

# Default cache configuration
config = {
    "CACHE_TYPE": os.environ.get("WIKIMORE_CACHE_TYPE", os.environ.get("CACHE_TYPE", "SimpleCache")),
    "CACHE_DEFAULT_TIMEOUT": int(os.environ.get("WIKIMORE_CACHE_TIMEOUT", os.environ.get("CACHE_TIMEOUT", 3600))),  # 1 hour default
}

# Redis configuration if available
if redis_url := os.environ.get("WIKIMORE_REDIS_URL", os.environ.get("REDIS_URL")):
    config.update({
        "CACHE_TYPE": "RedisCache",
        "CACHE_REDIS_URL": redis_url,
    })

# File system cache if specified
elif config["CACHE_TYPE"] == "FileSystemCache":
    cache_dir = os.environ.get("WIKIMORE_CACHE_DIR", os.environ.get("CACHE_DIR", "/tmp/wikimore_cache"))
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    config.update({
        "CACHE_DIR": cache_dir
    })

# Initialize cache
cache = Cache(config=config)