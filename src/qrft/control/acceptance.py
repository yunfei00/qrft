"""验收角色登记与只读证据，不提供远程文件读取或任意命令执行。"""

import time

from pydantic import BaseModel, Field


class NodeEvidence(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    machine_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    hostname: str = Field(min_length=1, max_length=200)
    video_path: str = Field(min_length=1, max_length=2048)


def register_routes(app, connection, require_token):
    from fastapi import Depends

    def schema(db):
        db.execute(
            "CREATE TABLE IF NOT EXISTS acceptance_nodes (node_id TEXT PRIMARY KEY, "
            "machine_id TEXT NOT NULL, hostname TEXT NOT NULL, video_path TEXT NOT NULL, "
            "registered_at REAL NOT NULL)"
        )

    @app.post("/acceptance/nodes", dependencies=[Depends(require_token)])
    def register(item: NodeEvidence):
        with connection() as db:
            schema(db)
            db.execute(
                "INSERT INTO acceptance_nodes VALUES (?,?,?,?,?) ON CONFLICT(node_id) "
                "DO UPDATE SET machine_id=excluded.machine_id,hostname=excluded.hostname,"
                "video_path=excluded.video_path,registered_at=excluded.registered_at",
                (item.node_id, item.machine_id, item.hostname, item.video_path, time.time()),
            )
        return {"status": "registered"}

    @app.get("/acceptance/nodes", dependencies=[Depends(require_token)])
    def nodes():
        with connection() as db:
            schema(db)
            return [dict(row) for row in db.execute("SELECT * FROM acceptance_nodes")]
