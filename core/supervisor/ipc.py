"""
IPC communication layer using Unix Domain Sockets and JSON Lines protocol.
"""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Union

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────
IPC_BUFFER_LIMIT = 16 * 1024 * 1024  # 16MB — default asyncio limit is 64KB


# ── Protocol Types ──────────────────────────────────────────────────

@dataclass
class IPCRequest:
    """IPC request from parent to child process."""

    id: str
    method: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to JSON line."""
        return json.dumps({
            "id": self.id,
            "method": self.method,
            "params": self.params
        }, default=str)

    @classmethod
    def from_json(cls, line: str) -> IPCRequest:
        """Deserialize from JSON line."""
        data = json.loads(line)
        return cls(
            id=data["id"],
            method=data["method"],
            params=data.get("params", {})
        )


@dataclass
class IPCResponse:
    """IPC response from child to parent process."""

    id: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    stream: bool = False
    chunk: str | None = None
    done: bool = False

    def to_json(self) -> str:
        """Serialize to JSON line."""
        data: dict[str, Any] = {"id": self.id}

        if self.stream:
            data["stream"] = True
            if self.chunk is not None:
                data["chunk"] = self.chunk
            if self.done:
                data["done"] = True
                if self.result is not None:
                    data["result"] = self.result
        elif self.error is not None:
            data["error"] = self.error
        elif self.result is not None:
            data["result"] = self.result

        return json.dumps(data, default=str)

    @classmethod
    def from_json(cls, line: str) -> IPCResponse:
        """Deserialize from JSON line."""
        data = json.loads(line)
        return cls(
            id=data["id"],
            result=data.get("result"),
            error=data.get("error"),
            stream=data.get("stream", False),
            chunk=data.get("chunk"),
            done=data.get("done", False)
        )


@dataclass
class IPCEvent:
    """Asynchronous event from child to parent (no request ID)."""

    event: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to JSON line."""
        return json.dumps({
            "event": self.event,
            "data": self.data
        }, default=str)

    @classmethod
    def from_json(cls, line: str) -> IPCEvent:
        """Deserialize from JSON line."""
        data = json.loads(line)
        return cls(
            event=data["event"],
            data=data.get("data", {})
        )


# ── IPC Server (Child Process) ────────────────────────────────────────

# Handler may return a single IPCResponse OR an AsyncIterator of IPCResponse
# for streaming.
RequestHandler = Callable[
    [IPCRequest],
    Awaitable[Union[IPCResponse, AsyncIterator[IPCResponse]]]
]


class IPCServer:
    """
    Unix Domain Socket server for child process.

    Listens on a socket file and handles incoming requests by dispatching
    to registered handlers.

    Supports both single-response and streaming-response handlers:
    - If handler returns an IPCResponse, a single JSON line is sent.
    - If handler returns an AsyncIterator[IPCResponse], each item is sent
      as a separate JSON line (streaming protocol).
    """

    def __init__(
        self,
        socket_path: Path,
        request_handler: RequestHandler
    ):
        self.socket_path = socket_path
        self.request_handler = request_handler
        self.server: asyncio.Server | None = None

    async def start(self) -> None:
        """Start the Unix socket server."""
        # Remove stale socket file if exists
        if self.socket_path.exists():
            self.socket_path.unlink()

        self.server = await asyncio.start_unix_server(
            self._handle_connection,
            path=str(self.socket_path),
            limit=IPC_BUFFER_LIMIT,
        )
        logger.info("IPC server started on %s", self.socket_path)

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ) -> None:
        """Handle a single client connection."""
        peer = writer.get_extra_info("peername", "unknown")
        logger.debug("IPC connection from %s", peer)

        try:
            while True:
                line_bytes = await reader.readline()
                if not line_bytes:
                    # Connection closed
                    break

                line = line_bytes.decode("utf-8").strip()
                if not line:
                    continue

                try:
                    request = IPCRequest.from_json(line)
                    logger.debug("IPC request: %s (id=%s)", request.method, request.id)

                    handler_result = await self.request_handler(request)

                    # Check if result is an async iterator (streaming)
                    if hasattr(handler_result, "__aiter__"):
                        async for response in handler_result:
                            response_line = response.to_json() + "\n"
                            writer.write(response_line.encode("utf-8"))
                            await writer.drain()
                    else:
                        response_line = handler_result.to_json() + "\n"
                        writer.write(response_line.encode("utf-8"))
                        await writer.drain()

                except json.JSONDecodeError as e:
                    logger.error("Invalid JSON in IPC request: %s", e)
                    error_response = IPCResponse(
                        id="unknown",
                        error={"code": "INVALID_JSON", "message": str(e)}
                    )
                    writer.write((error_response.to_json() + "\n").encode("utf-8"))
                    await writer.drain()
                except Exception as e:
                    logger.exception("Error handling IPC request: %s", e)
                    error_response = IPCResponse(
                        id=request.id if "request" in locals() else "unknown",
                        error={"code": "HANDLER_ERROR", "message": str(e)}
                    )
                    writer.write((error_response.to_json() + "\n").encode("utf-8"))
                    await writer.drain()

        except asyncio.CancelledError:
            logger.info("IPC connection cancelled")
        except Exception as e:
            logger.exception("IPC connection error: %s", e)
        finally:
            writer.close()
            await writer.wait_closed()
            logger.debug("IPC connection closed: %s", peer)

    async def stop(self) -> None:
        """Stop the server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("IPC server stopped")

        # Clean up socket file
        if self.socket_path.exists():
            self.socket_path.unlink()


# ── IPC Client (Parent Process) ────────────────────────────────────────

class IPCClient:
    """
    Unix Domain Socket client for parent process.

    Connects to a child process socket and sends requests.
    """

    def __init__(self, socket_path: Path):
        self.socket_path = socket_path
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    @staticmethod
    def _resolve_ipc_timeout() -> float:
        """Resolve IPC stream timeout from config, with fallback default."""
        try:
            from core.config import load_config
            config = load_config()
            return float(config.server.ipc_stream_timeout)
        except Exception:
            return 60.0

    async def connect(self, timeout: float = 5.0) -> None:
        """Connect to the Unix socket."""
        async with asyncio.timeout(timeout):
            self.reader, self.writer = await asyncio.open_unix_connection(
                path=str(self.socket_path),
                limit=IPC_BUFFER_LIMIT,
            )
            logger.debug("IPC client connected to %s", self.socket_path)

    async def send_request(
        self,
        request: IPCRequest,
        timeout: float = 60.0
    ) -> IPCResponse:
        """
        Send a request and wait for response.

        Args:
            request: The request to send
            timeout: Timeout in seconds

        Returns:
            The response

        Raises:
            asyncio.TimeoutError: If timeout exceeded
            RuntimeError: If not connected
        """
        if not self.reader or not self.writer:
            raise RuntimeError("Not connected")

        async with self._lock:
            # Send request
            request_line = request.to_json() + "\n"
            self.writer.write(request_line.encode("utf-8"))
            await self.writer.drain()
            logger.debug("IPC request sent: %s (id=%s)", request.method, request.id)

            # Wait for response
            async with asyncio.timeout(timeout):
                response_line_bytes = await self.reader.readline()
                if not response_line_bytes:
                    raise RuntimeError("Connection closed")

                response_line = response_line_bytes.decode("utf-8").strip()
                response = IPCResponse.from_json(response_line)
                logger.debug("IPC response received: id=%s", response.id)

                return response

    async def send_request_stream(
        self,
        request: IPCRequest,
        timeout: float | None = None,
    ) -> AsyncIterator[IPCResponse]:
        """
        Send a request and yield streaming responses.

        Reads JSON lines until a response with done=True is received.
        Each intermediate chunk has stream=True and a chunk field.
        The final response has stream=True, done=True, and a result field.

        Args:
            request: The request to send
            timeout: Per-chunk timeout in seconds. Resets on each received chunk.
                If None, reads from ``config.json server.ipc_stream_timeout``
                (default 60s).

        Yields:
            IPCResponse objects (chunks and final result)

        Raises:
            asyncio.TimeoutError: If timeout exceeded
            RuntimeError: If not connected
        """
        if timeout is None:
            timeout = self._resolve_ipc_timeout()
        if not self.reader or not self.writer:
            raise RuntimeError("Not connected")

        async with self._lock:
            # Send request
            request_line = request.to_json() + "\n"
            self.writer.write(request_line.encode("utf-8"))
            await self.writer.drain()
            logger.debug("IPC stream request sent: %s (id=%s)", request.method, request.id)

            # Read streaming responses until done
            while True:
                response_line_bytes = await asyncio.wait_for(
                    self.reader.readline(),
                    timeout=timeout,
                )
                if not response_line_bytes:
                    raise RuntimeError("Connection closed during stream")

                response_line = response_line_bytes.decode("utf-8").strip()
                if not response_line:
                    continue

                response = IPCResponse.from_json(response_line)

                # Non-streaming response (error or unexpected)
                if not response.stream:
                    yield response
                    return

                yield response

                # Final chunk with done=True ends the stream
                if response.done:
                    return

    async def close(self) -> None:
        """Close the connection."""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            logger.debug("IPC client disconnected from %s", self.socket_path)
