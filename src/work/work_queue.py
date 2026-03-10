from redis import Redis
from rq import Queue

from ..utils.configs import sysconfig

lq = Queue(
    "layers",
    connection=Redis(
        host=sysconfig.get("redis", "host"), port=sysconfig.getint("redis", "port")
    ),
)

iq = Queue(
    "id",
    connection=Redis(
        host=sysconfig.get("redis", "host"), port=sysconfig.getint("redis", "port")
    ),
)
