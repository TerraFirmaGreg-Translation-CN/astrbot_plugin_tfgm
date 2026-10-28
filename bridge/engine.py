"""All bridge activity lives in this plugin; no Minecraft platform registration."""

import asyncio
import hashlib
import random
import time
from uuid import UUID

import aiohttp

from .messages import allowed, chunks, clean, format_text, select_text
from .sidecar import Sidecar, SidecarError
from .store import Store


def identifier(*parts):
    return hashlib.sha256("\0".join(map(str, parts)).encode()).hexdigest()


class Engine:
    def __init__(self, settings, data_path, send_qq, generate, logger):
        self.settings, self.send_qq, self.generate, self.log = settings, send_qq, generate, logger
        self.store = Store(data_path)
        self.tasks = []
        self.clients = {}
        self.health = {}
        self.errors = {}
        self.session = None
        self.stopping = False
        self.route_map = {r["id"]: r for r in settings.routes}

    async def start(self):
        if not self.settings.enabled:
            return
        self.session = aiohttp.ClientSession()
        for sid, server in self.settings.servers.items():
            self.clients[sid] = Sidecar(
                self.session, server, self.settings.connection["timeout_seconds"]
            )
            self.tasks.append(asyncio.create_task(self.poll(sid), name=f"tfgm-poll-{sid}"))
            self.tasks.append(
                asyncio.create_task(self.worker("mc:" + sid), name=f"tfgm-send-{sid}")
            )
            if self.settings.ai["enabled"] and server["ai_enabled"]:
                for n in range(self.settings.ai["concurrency"]):
                    self.tasks.append(
                        asyncio.create_task(self.worker("ai:" + sid), name=f"tfgm-ai-{sid}-{n}")
                    )
        for origin in {r["qq_origin"] for r in self.settings.routes}:
            self.tasks.append(asyncio.create_task(self.worker("qq:" + origin), name="tfgm-qq"))
        self.tasks.append(asyncio.create_task(self.maintenance(), name="tfgm-prune"))

    async def stop(self):
        self.stopping = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.session:
            await self.session.close()
        self.store.close()

    def report(self, target, code):
        # Log codes only. URLs, tokens, provider errors and chat contents are excluded.
        if self.errors.get(target) != code:
            self.log.warning("TFGM %s: %s", target, code)
        self.errors[target] = code

    async def maintenance(self):
        while True:
            self.store.prune(
                self.settings.delivery["retention_hours"], self.settings.ai["history_hours"]
            )
            await asyncio.sleep(60)

    async def poll_once(self, sid):
        server = self.settings.servers[sid]
        client = self.clients[sid]
        now = time.monotonic()
        health, checked = self.health.get(sid, ({}, 0))
        if now - checked >= self.settings.connection["health_seconds"]:
            health = await client.health()
            self.health[sid] = health, now
            if not health.get("messages", {}).get("enabled"):
                self.report(sid + ":delivery", "messages_disabled")
            else:
                self.errors.pop(sid + ":delivery", None)
        cursor = self.store.cursor(sid, server["url"])
        if cursor is None:
            with self.store.db:
                self.store.set_cursor(
                    sid,
                    server["url"],
                    health["instance_id"],
                    0 if self.settings.connection["initial_history"] else health["last_event_seq"],
                )
            cursor = self.store.cursor(sid, server["url"])
        # Read using stored cursor first, so an instance transition is discovered even between health probes.
        data = await client.events(cursor["seq"], self.settings.connection["batch_size"])
        if data["instance_id"] != cursor["instance"]:
            data = await client.events(0, self.settings.connection["batch_size"])
            cursor = {"seq": 0, "instance": data["instance_id"]}
        instance = data["instance_id"]
        seq = cursor["seq"]
        with self.store.db:
            for event in data["events"]:
                event_seq = event.get("seq")
                if type(event_seq) is not int or event_seq <= seq:
                    raise SidecarError("unordered_events")
                if event_seq > seq + 1:
                    self.store.count("event_gap", event_seq - seq - 1)
                seq = event_seq
                try:
                    self.on_game(sid, instance, event)
                except (ValueError, TypeError, KeyError):
                    self.store.count("invalid_event")
            self.store.set_cursor(sid, server["url"], instance, seq)
        self.errors.pop(sid, None)
        return bool(data.get("truncated"))

    async def poll(self, sid):
        failures = 0
        while True:
            try:
                more = await self.poll_once(sid)
                failures = 0
                await asyncio.sleep(0.01 if more else self.settings.connection["poll_seconds"])
            except asyncio.CancelledError:
                raise
            except Exception as e:
                failures += 1
                self.report(sid, e.code if isinstance(e, SidecarError) else type(e).__name__)
                await asyncio.sleep(
                    min(2 ** min(failures, 8), self.settings.connection["retry_seconds"])
                    * random.uniform(0.8, 1.2)
                )

    def enqueue(self, key, target, kind, payload, created=None):
        d = self.settings.delivery
        return self.store.enqueue(
            key, target, kind, payload, d["ttl_seconds"], d["queue_capacity"], created
        )

    def qq_jobs(self, key, sid, route, text, created=None):
        d = self.settings.delivery
        for n, part in enumerate(chunks(text, d["chunk_chars"], d["max_chunks"])):
            self.enqueue(
                identifier(key, route["id"], n),
                "qq:" + route["qq_origin"],
                "qq",
                {
                    "server": sid,
                    "endpoint": self.settings.servers[sid]["url"],
                    "route": route["id"],
                    "origin": route["qq_origin"],
                    "text": part,
                },
                created,
            )

    def mc_jobs(self, key, sid, text, player=None, color="white", route=None, created=None):
        d = self.settings.delivery
        for n, part in enumerate(chunks(text, d["chunk_chars"], d["max_chunks"])):
            request_id = identifier(key, n)
            payload = {
                "server": sid,
                "endpoint": self.settings.servers[sid]["url"],
                "body": {
                    "request_id": request_id,
                    "target": {"type": "players", "uuids": [player]} if player else {"type": "all"},
                    "message": {"text": part, "color": color},
                },
            }
            if route:
                payload.update(route=route["id"], origin=route["qq_origin"])
            self.enqueue(request_id, "mc:" + sid, "mc", payload, created)

    def on_game(self, sid, instance, event):
        kind = event["type"]
        created = float(event["timestampMs"]) / 1000
        if created + self.settings.delivery["ttl_seconds"] <= time.time():
            self.store.count("expired")
            return
        if created > time.time() + 60:
            self.store.count("future_event")
            return
        key = identifier(sid, instance, event["seq"])
        player = str(UUID(event["uuid"])) if event.get("uuid") else ""
        name = clean(event.get("name") or player)
        message = clean(event.get("data", {}).get("message", ""))
        ai = self.settings.ai
        is_ai = (
            kind == "player_chat"
            and ai["enabled"]
            and self.settings.servers[sid]["ai_enabled"]
            and message.startswith(ai["prefix"])
        )
        if is_ai and player:
            prompt = message[len(ai["prefix"]) :].strip()
            if prompt and allowed(player, ai["allowed_players"], ai["denied_players"]):
                session = sid + ":" + player
                pending = self.store.db.execute(
                    "SELECT 1 FROM jobs WHERE kind='ai' AND status IN ('pending','working') AND json_extract(payload,'$.session')=?",
                    (session,),
                ).fetchone()
                recent = self.store.db.execute(
                    "SELECT MAX(created) FROM jobs WHERE kind='ai' AND json_extract(payload,'$.session')=?",
                    (session,),
                ).fetchone()[0]
                if pending or (recent and time.time() - recent < ai["cooldown_seconds"]):
                    self.mc_jobs(key + "busy", sid, "[小助手] 请稍后再提问。", player)
                elif len(prompt) > ai["max_input_chars"]:
                    self.mc_jobs(key + "long", sid, "[小助手] 问题太长，请缩短后重试。", player)
                else:
                    self.enqueue(
                        key + ":ai",
                        "ai:" + sid,
                        "ai",
                        {
                            "server": sid,
                            "endpoint": self.settings.servers[sid]["url"],
                            "player": player,
                            "session": session,
                            "name": name,
                            "prompt": prompt,
                        },
                        created,
                    )
        for r in self.settings.routes:
            if (
                r["server_id"] != sid
                or not r["mc_to_qq"]
                or not allowed(player, r["allowed_players"], r["denied_players"])
            ):
                continue
            if kind == "player_chat":
                if is_ai and not ai["forward_questions"]:
                    continue
                text = select_text(message, r, "mc")
                if text is None:
                    continue
            elif kind in ("player_join", "player_leave") and r["join_leave"]:
                text = "加入了游戏" if kind == "player_join" else "离开了游戏"
            elif kind == "player_death" and r["death"]:
                text = "死亡了（" + clean(event.get("data", {}).get("source", "未知原因")) + "）"
            else:
                continue
            self.qq_jobs(
                key,
                sid,
                r,
                format_text(r["mc_template"], self.settings.servers[sid]["name"], name, text),
                created,
            )

    def on_qq(self, origin, message_id, sender, nickname, text_for_route):
        if not self.settings.enabled or self.stopping:
            return
        with self.store.db:
            for r in self.settings.routes:
                if (
                    r["qq_origin"] != origin
                    or not r["qq_to_mc"]
                    or not allowed(sender, r["allowed_qq"], r["ignored_qq"])
                ):
                    continue
                text = select_text(text_for_route(r), r, "qq")
                if text is None:
                    continue
                sid = r["server_id"]
                key = identifier("qq", origin, message_id, r["id"])
                self.mc_jobs(
                    key,
                    sid,
                    format_text(
                        r["qq_template"], self.settings.servers[sid]["name"], nickname, text
                    ),
                    color=r["mc_color"],
                    route=r,
                )

    def valid_job(self, job):
        p = job["payload"]
        server = self.settings.servers.get(p["server"])
        if not server or (p.get("endpoint") and p["endpoint"] != server["url"]):
            return False
        if "route" in p:
            route = self.route_map.get(p["route"])
            if not route or route["server_id"] != p["server"] or route["qq_origin"] != p["origin"]:
                return False
            if not route["mc_to_qq" if job["kind"] == "qq" else "qq_to_mc"]:
                return False
        return True

    async def deliver_mc(self, job):
        p = job["payload"]
        client = self.clients[p["server"]]
        health = await client.health()
        if not health.get("messages", {}).get("enabled"):
            raise SidecarError("messages_disabled")
        if p.get("instance") and p["instance"] != health["instance_id"]:
            raise SidecarError("instance_changed_ambiguous")
        p["instance"] = health["instance_id"]
        # Persist the instance before issuing a request that could reach the server.
        self.store.save_payload(job, p)
        data = await client.send(p["body"])
        if data["instance_id"] != p["instance"]:
            raise SidecarError("instance_changed_ambiguous")
        if data["status"] == "processing":
            raise SidecarError("processing", retry=True, ambiguous=True)
        if data["delivered_count"] == 0:
            raise SidecarError("no_online_recipients")
        if data.get("offline_uuids"):
            self.report(job["target"], "partial_offline")

    async def run_ai(self, job):
        p, ai = job["payload"], self.settings.ai
        sid, player = p["server"], p["player"]
        if not ai["enabled"] or not self.settings.servers[sid]["ai_enabled"]:
            raise SidecarError("ai_disabled")
        if not allowed(player, ai["allowed_players"], ai["denied_players"]):
            raise SidecarError("ai_player_denied")
        if p["prompt"] == ai["reset_word"]:
            with self.store.db:
                self.store.save_history(p["session"], [])
                self.mc_jobs(job["id"] + ":reset", sid, "[小助手] 已重置对话。", player)
            return
        if ai["show_thinking"]:
            with self.store.db:
                self.mc_jobs(job["id"] + ":thinking", sid, ai["thinking_text"], player)
        history = self.store.history(p["session"], ai["history_hours"])
        history = history[-2 * ai["history_turns"] :] if ai["history_turns"] else []
        try:
            answer = await asyncio.wait_for(
                self.generate(p["prompt"], history, ai), ai["timeout_seconds"]
            )
            if not answer or not answer.strip():
                raise ValueError("empty_response")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.report(
                "ai:" + sid, "timeout" if isinstance(e, TimeoutError) else "generation_failed"
            )
            with self.store.db:
                self.mc_jobs(
                    job["id"] + ":error", sid, "[小助手] 暂时无法回答，请稍后重试。", player
                )
            raise SidecarError("generation_failed") from None
        answer = clean(answer)
        if len(answer) > ai["max_reply_chars"]:
            answer = answer[: ai["max_reply_chars"] - 5] + "…[截断]"
        with self.store.db:
            if ai["history_turns"]:
                history += [
                    {"role": "user", "content": p["prompt"]},
                    {"role": "assistant", "content": answer},
                ]
                self.store.save_history(p["session"], history[-2 * ai["history_turns"] :])
            self.mc_jobs(
                job["id"] + ":answer",
                sid,
                ai["reply_prefix"] + answer,
                player if ai["reply_scope"] == "player" else None,
            )
            if ai["forward_replies"]:
                for r in self.settings.routes:
                    if (
                        r["server_id"] == sid
                        and r["mc_to_qq"]
                        and allowed(player, r["allowed_players"], r["denied_players"])
                    ):
                        self.qq_jobs(
                            job["id"] + ":answer",
                            sid,
                            r,
                            format_text(
                                r["mc_template"],
                                self.settings.servers[sid]["name"],
                                "小助手 → " + p["name"],
                                answer,
                            ),
                        )

    async def process(self, job):
        if not self.valid_job(job):
            self.store.finish(job, "failed", "configuration_changed")
            return
        try:
            if job["kind"] == "qq":
                found = await asyncio.wait_for(
                    self.send_qq(job["payload"]["origin"], job["payload"]["text"]),
                    self.settings.connection["timeout_seconds"],
                )
                if found is False:
                    raise SidecarError("qq_platform_not_found")
            elif job["kind"] == "mc":
                await self.deliver_mc(job)
            else:
                await self.run_ai(job)
            self.store.finish(job)
            self.errors.pop(job["target"], None)
        except asyncio.CancelledError:
            # Store recovery distinguishes MC idempotency from ambiguous QQ/AI sends.
            raise
        except Exception as e:
            code = e.code if isinstance(e, SidecarError) else type(e).__name__
            self.report(job["target"], code)
            if (
                job["kind"] == "mc"
                and isinstance(e, SidecarError)
                and e.retry
                and job["attempts"] < self.settings.delivery["attempts"]
                and time.time() + 2 < job["expires"]
            ):
                self.store.retry(job, job["payload"], min(2 ** job["attempts"], 10))
            else:
                self.store.finish(job, "failed", code)

    async def worker(self, target):
        while True:
            job = self.store.claim(target)
            if job is None:
                await asyncio.sleep(0.2)
                continue
            await self.process(job)
            await asyncio.sleep(
                self.settings.delivery["interval_seconds"] if job["kind"] != "ai" else 0
            )

    def status(self):
        lines = ["TFGM 桥接：" + ("已启用" if self.settings.enabled else "未启用")]
        for sid in self.settings.servers:
            health, _ = self.health.get(sid, ({}, 0))
            state = self.errors.get(sid, "已连接" if health else "等待连接")
            send = "开启" if health.get("messages", {}).get("enabled") else "未开启/未知"
            lines.append(
                f"{sid}：{state}；消息接口{send}；版本 {health.get('mod_version', '未知')}"
            )
        lines.append(f"路由 {len(self.settings.routes)} 条")
        summary = self.store.summary()
        pending = sum(
            r["count"] for r in summary["queues"] if r["status"] in ("pending", "working")
        )
        lines.append(f"待处理 {pending}；计数 {summary['counters']}")
        lines.extend(f"{target}：{code}" for target, code in self.errors.items())
        dead = sum(t.done() and not t.cancelled() for t in self.tasks)
        if dead:
            lines.append(f"后台任务异常退出：{dead}，请重载插件并检查日志")
        return "\n".join(lines)
