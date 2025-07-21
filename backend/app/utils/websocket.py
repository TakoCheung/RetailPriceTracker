from fastapi import WebSocket

async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    await ws.send_text("Connected to price updates")
    try:
        while True:
            await ws.receive_text()
            await ws.send_text("No updates yet")
    except Exception:
        await ws.close()
