from redis import Redis
from rq import Worker

from src.utils.configs import sysconfig

wredis = Redis(
    host=sysconfig.get("redis", "host"), port=sysconfig.getint("redis", "port")
)

w = Worker(["layers", "id"], connection=wredis)

if __name__ == "__main__":
    w.work()
