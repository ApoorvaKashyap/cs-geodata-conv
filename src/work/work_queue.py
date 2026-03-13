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


def get_status(task_id: str) -> dict[str, str]:
    task = lq.fetch_job(task_id)
    if not task:
        task = iq.fetch_job(task_id)
    if not task:
        return {"status": "not found"}
    return {"status": task._status}
