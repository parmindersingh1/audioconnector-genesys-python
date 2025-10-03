# agent_media_service_with_ws.py
import asyncio
import importlib
import logging
import os
import secrets
import json
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

logger = logging.getLogger("agent_media_ws")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI()

# ----- Load generated proto module (livekit.protocol.agent) -----
def load_agent_proto():
    candidates = [
        "livekit.protocol.agent",
        "livekit_agent_pb2",
        "livekit.protocol.agent_pb2",
    ]
    for name in candidates:
        try:
            mod = importlib.import_module(name)
            logger.info("Imported proto module: %s", name)
            return mod
        except Exception:
            pass
    raise RuntimeError(
        "Could not import LiveKit agent proto. Ensure generated stubs are on PYTHONPATH."
    )

agent_pb2 = None
# Try to import, if present (we keep previous behavior)
try:
    agent_pb2 = load_agent_proto()
except Exception:
    logger.warning("LiveKit agent proto not available; agent/media endpoints that rely on it will fail.")


# ----- Global state (same pattern as earlier agent_media_service) -----
active_workers: Dict[str, Dict] = {}
media_jobs: Dict[str, Dict] = {}

SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("PORT", "8080"))

# For the added /ws: API key expected can be set in env var AUDIO_API_KEY
AUDIO_API_KEY = os.environ.get("AUDIO_API_KEY")  # if None -> accept any key (testing convenience)


# -----------------------
# Existing /agent and /media endpoints (keep previous behavior)
# For brevity I provide minimal but functional /agent handler if agent_pb2 exists.
# If you already have a full implementation, keep that and only add /ws endpoint.
# -----------------------

if agent_pb2:
    @app.websocket("/agent")
    async def agent_ws(websocket: WebSocket):
        await websocket.accept()
        peer = websocket.client
        logger.info("Accepted /agent connection from %s", peer)

        try:
            first_bytes = await websocket.receive_bytes()
        except WebSocketDisconnect:
            logger.info("Client disconnected before register: %s", peer)
            return
        except Exception as ex:
            logger.exception("Failed to receive first (binary) frame from %s: %s", peer, ex)
            try:
                await websocket.close()
            except Exception:
                pass
            return

        try:
            wmsg = agent_pb2.WorkerMessage()
            wmsg.ParseFromString(first_bytes)
        except Exception as ex:
            logger.exception("Failed to parse WorkerMessage: %s", ex)
            await websocket.close()
            return

        if not wmsg.HasField("register"):
            logger.error("First WorkerMessage missing register")
            await websocket.close()
            return

        worker_id = f"worker-{secrets.token_hex(4)}"
        server_msg = agent_pb2.ServerMessage()
        server_msg.register.worker_id = worker_id
        try:
            await websocket.send_bytes(server_msg.SerializeToString())
        except Exception:
            await websocket.close()
            return

        active_workers[worker_id] = {"ws": websocket, "info": wmsg.register}
        logger.info("Registered worker %s", worker_id)

        try:
            while True:
                try:
                    b = await websocket.receive_bytes()
                except WebSocketDisconnect:
                    logger.info("Worker disconnected: %s", worker_id)
                    break
                except Exception as e:
                    logger.exception("Error receiving bytes from worker %s: %s", worker_id, e)
                    break

                try:
                    wm = agent_pb2.WorkerMessage()
                    wm.ParseFromString(b)
                except Exception:
                    logger.exception("Failed to parse WorkerMessage for %s", worker_id)
                    continue

                if wm.HasField("ping"):
                    pong = agent_pb2.ServerMessage()
                    try:
                        pong.pong.last_timestamp = wm.ping.timestamp
                        pong.pong.timestamp = int(asyncio.get_event_loop().time() * 1000)
                        await websocket.send_bytes(pong.SerializeToString())
                    except Exception:
                        logger.debug("Failed to reply pong")
                    continue

                logger.info("Worker %s message: %s", worker_id, wm)
        finally:
            active_workers.pop(worker_id, None)
            try:
                await websocket.close()
            except Exception:
                pass


# Minimal /assign_job and /media implementations (same shape as earlier file) --
# include them only if agent_pb2 exists; otherwise keep them out.
if agent_pb2:
    @app.post("/assign_job")
    async def assign_job(request: Request):
        body = await request.json()
        worker_id = body.get("worker_id")
        job_id = body.get("job_id")
        if not worker_id or not job_id:
            raise HTTPException(status_code=400, detail="worker_id and job_id required")
        w = active_workers.get(worker_id)
        if not w:
            raise HTTPException(status_code=404, detail="worker not found")
        token = secrets.token_urlsafe(16)
        url = f"ws://{SERVER_HOST}:{SERVER_PORT}/media/{job_id}?role=worker&token={token}"
        sm = agent_pb2.ServerMessage()
        sm.assignment.url = url
        sm.assignment.token = token
        try:
            sm.assignment.job.id = job_id
        except Exception:
            pass
        try:
            await w["ws"].send_bytes(sm.SerializeToString())
        except Exception as e:
            logger.exception("Failed to send assignment: %s", e)
            raise HTTPException(status_code=500, detail="failed to send assignment")
        media_jobs[job_id] = {"worker_media_ws": None, "client_media_ws": None, "relay_tasks": [], "token": token}
        return JSONResponse({"ok": True, "job_id": job_id, "url": url, "token": token})

    @app.websocket("/media/{job_id}")
    async def media_ws(websocket: WebSocket, job_id: str):
        await websocket.accept()
        qp = websocket.query_params
        qs_role = qp.get("role", "client")
        qs_token = qp.get("token")
        mj = media_jobs.get(job_id)
        if not mj:
            await websocket.close(code=4000)
            return
        if qs_token != mj.get("token"):
            await websocket.close(code=4001)
            return

        role_norm = qs_role.lower()
        if role_norm == "worker":
            if mj["worker_media_ws"] is not None:
                await websocket.close(code=4002)
                return
            mj["worker_media_ws"] = websocket
        else:
            if mj["client_media_ws"] is not None:
                await websocket.close(code=4003)
                return
            mj["client_media_ws"] = websocket

        if mj["worker_media_ws"] and mj["client_media_ws"] and not mj["relay_tasks"]:
            t1 = asyncio.create_task(relay_binary(job_id, mj["worker_media_ws"], mj["client_media_ws"], "worker->client"))
            t2 = asyncio.create_task(relay_binary(job_id, mj["client_media_ws"], mj["worker_media_ws"], "client->worker"))
            mj["relay_tasks"] = [t1, t2]

        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            try:
                for t in mj.get("relay_tasks", []):
                    t.cancel()
            except Exception:
                pass
            try:
                if mj.get("worker_media_ws") and mj["worker_media_ws"] != websocket:
                    await mj["worker_media_ws"].close()
            except Exception:
                pass
            try:
                if mj.get("client_media_ws") and mj["client_media_ws"] != websocket:
                    await mj["client_media_ws"].close()
            except Exception:
                pass
            media_jobs.pop(job_id, None)

    async def relay_binary(job_id: str, src: WebSocket, dst: WebSocket, label: str):
        try:
            while True:
                try:
                    data = await src.receive_bytes()
                except WebSocketDisconnect:
                    break
                except Exception:
                    break
                try:
                    await dst.send_bytes(data)
                except Exception:
                    break
        finally:
            pass


# -----------------------
# New: /ws endpoint to satisfy your AudioTester
# -----------------------
@app.websocket("/ws")
async def audio_connector_ws(websocket: WebSocket):
    """
    Accept test client's websocket for audio:
    - Validate X-API-KEY if AUDIO_API_KEY env is set.
    - When client sends JSON 'open', reply with JSON 'opened'.
    - Echo binary audio back to the client (simulate audio output).
    - After receiving enough audio, send an 'event' transcript JSON.
    """
    # Read headers (they are available before accept)
    headers = websocket.headers
    client_api_key = headers.get("x-api-key") or headers.get("X-API-KEY") or headers.get("X-Api-Key")
    session_id = headers.get("audiohook-session-id")
    org_id = headers.get("audiohook-organization-id")
    correlation_id = headers.get("audiohook-correlation-id")

    # Validate API key if set in env
    if AUDIO_API_KEY:
        if not client_api_key or client_api_key != AUDIO_API_KEY:
            # reject by closing gently - websocket handshake already done for many clients,
            # but some clients will see "Unexpected server response: 403" if we return without accept.
            # FastAPI/Starlette does not provide an easy way to return an HTTP 403 after handshake attempt,
            # so we just close with a close code and log the reason.
            logger.warning("Rejecting /ws connection due to invalid API key (got=%s)", client_api_key)
            # perform a concise reject: don't accept; however, `websocket.close()` only works after accept.
            # To make client error consistent, raise an exception that results in 403 response during handshake:
            # FastAPI can't raise HTTPException from a websocket handler to set the HTTP status.
            # Instead, close with normal code 1008 (policy violation) after accept to inform client.
            try:
                await websocket.accept()
                await websocket.close(code=1008)
            except Exception:
                pass
            return

    # Accept connection
    await websocket.accept()
    peer = websocket.client
    logger.info("Accepted /ws connection from %s (session=%s, org=%s)", peer, session_id, org_id)

    # State
    audio_chunks_received = 0
    total_bytes = 0
    transcript_sent = False

    try:
        while True:
            msg = await websocket.receive()

            # disconnect
            if msg["type"] == "websocket.disconnect":
                logger.info("/ws disconnect from %s", peer)
                break

            # text message
            if "text" in msg and msg["text"] is not None:
                raw = msg["text"]
                # try parse json
                try:
                    j = json.loads(raw)
                except Exception:
                    logger.debug("Received non-json text on /ws: %s", raw)
                    continue

                mtype = j.get("type")
                logger.info("Received JSON message on /ws: %s", mtype)
                if mtype == "open":
                    # Reply with opened message
                    opened = {
                        "id": j.get("id"),
                        "version": j.get("version"),
                        "seq": j.get("seq", 0),
                        "serverseq": 1,
                        "type": "opened",
                        "parameters": {"message": "welcome", "session_id": session_id},
                    }
                    await websocket.send_text(json.dumps(opened))
                    logger.info("Sent opened response on /ws")
                else:
                    # echo back control message ack
                    ack = {
                        "id": j.get("id"),
                        "version": j.get("version"),
                        "seq": j.get("seq", 0),
                        "serverseq": 1,
                        "type": "ack",
                        "parameters": {"echo": True},
                    }
                    await websocket.send_text(json.dumps(ack))

            # binary message
            elif "bytes" in msg and msg["bytes"] is not None:
                data = msg["bytes"]
                audio_chunks_received += 1
                total_bytes += len(data)
                # Echo the same chunk back (simulate UltraVox audio output)
                try:
                    await websocket.send_bytes(data)
                except Exception:
                    logger.exception("Failed to send bytes back to client")
                # After some amount of audio accumulated, send a transcript event once
                if not transcript_sent and total_bytes > 1000:
                    transcript_evt = {
                        "id": session_id or "session-test",
                        "version": "2",
                        "seq": audio_chunks_received,
                        "serverseq": 1,
                        "type": "event",
                        "parameters": {
                            "entities": [
                                {
                                    "type": "transcript",
                                    "data": {
                                        "alternatives": [
                                            {
                                                "interpretations": [
                                                    {
                                                        "transcript": "hello from server (simulated)"
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                }
                            ]
                        },
                    }
                    await websocket.send_text(json.dumps(transcript_evt))
                    transcript_sent = True
            else:
                # unknown message shape
                logger.debug("Unknown websocket.receive() payload on /ws: %s", msg)
    except WebSocketDisconnect:
        logger.info("/ws client disconnected")
    except Exception as e:
        logger.exception("Exception in /ws handler: %s", e)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("/ws handler finished (session=%s) - chunks=%d bytes=%d", session_id, audio_chunks_received, total_bytes)


if __name__ == "__main__":
    # Stop any previously-running server and run this.
    uvicorn.run("agent_media_service:app", host="0.0.0.0", port=SERVER_PORT, log_level="info")
