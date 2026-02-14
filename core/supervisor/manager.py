"""
Process Supervisor - Manages lifecycle of Person child processes.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from core.supervisor.ipc import IPCResponse
from core.supervisor.process_handle import ProcessHandle, ProcessState

logger = logging.getLogger(__name__)


# ── Configuration ──────────────────────────────────────────────────

@dataclass
class RestartPolicy:
    """Process restart policy configuration."""
    max_retries: int = 5                   # Maximum restart attempts
    backoff_base_sec: float = 2.0          # Initial backoff delay
    backoff_max_sec: float = 60.0          # Maximum backoff delay
    reset_after_sec: float = 300.0         # Stable runtime to reset counter


@dataclass
class HealthConfig:
    """Health check configuration."""
    ping_interval_sec: float = 10.0        # Ping interval
    ping_timeout_sec: float = 5.0          # Ping timeout
    max_missed_pings: int = 3              # Consecutive misses before hang
    startup_grace_sec: float = 30.0        # Grace period after startup


# ── Process Supervisor ─────────────────────────────────────────────

class ProcessSupervisor:
    """
    Supervisor for managing Person child processes.

    Responsibilities:
    - Start/stop child processes
    - Health monitoring (ping/pong)
    - Hang detection and recovery (SIGKILL + restart)
    - Auto-restart with exponential backoff
    - Schedule coordination (heartbeat/cron triggers)
    """

    def __init__(
        self,
        persons_dir: Path,
        shared_dir: Path,
        run_dir: Path,
        log_dir: Path | None = None,
        restart_policy: RestartPolicy | None = None,
        health_config: HealthConfig | None = None
    ):
        self.persons_dir = persons_dir
        self.shared_dir = shared_dir
        self.run_dir = run_dir
        self.log_dir = log_dir

        self.restart_policy = restart_policy or RestartPolicy()
        self.health_config = health_config or HealthConfig()

        self.processes: dict[str, ProcessHandle] = {}
        self._health_check_task: asyncio.Task | None = None
        self._shutdown = False
        self._restart_counts: dict[str, int] = {}
        self._restarting: set[str] = set()

    async def start_all(self, person_names: list[str]) -> None:
        """
        Start all Person processes.

        Args:
            person_names: List of person names to start
        """
        logger.info(f"Starting {len(person_names)} Person processes")

        # Create socket directory
        socket_dir = self.run_dir / "sockets"
        socket_dir.mkdir(parents=True, exist_ok=True)

        # Start each process
        for person_name in person_names:
            await self.start_person(person_name)

        # Start health check loop
        self._health_check_task = asyncio.create_task(
            self._health_check_loop()
        )

        logger.info("All processes started")

    async def start_person(self, person_name: str) -> None:
        """Start a single Person process."""
        if person_name in self.processes:
            logger.warning(f"Process already exists: {person_name}")
            return

        socket_dir = self.run_dir / "sockets"
        socket_dir.mkdir(parents=True, exist_ok=True)
        socket_path = socket_dir / f"{person_name}.sock"

        handle = ProcessHandle(
            person_name=person_name,
            socket_path=socket_path,
            persons_dir=self.persons_dir,
            shared_dir=self.shared_dir,
            log_dir=self.log_dir
        )

        try:
            await handle.start()
            self.processes[person_name] = handle
            logger.info(f"Person process started: {person_name} (PID {handle.get_pid()})")

        except Exception as e:
            logger.error(f"Failed to start process {person_name}: {e}")
            raise

    async def stop_person(self, person_name: str) -> None:
        """Stop a single Person process."""
        handle = self.processes.get(person_name)
        if not handle:
            logger.warning(f"Process not found: {person_name}")
            return

        await handle.stop(timeout=10.0)
        del self.processes[person_name]
        logger.info(f"Person process stopped: {person_name}")

    async def restart_person(self, person_name: str) -> None:
        """Restart a Person process."""
        logger.info(f"Restarting process: {person_name}")

        # Stop existing process
        if person_name in self.processes:
            await self.stop_person(person_name)

        # Start new process
        await self.start_person(person_name)

    async def shutdown_all(self) -> None:
        """Shutdown all processes gracefully."""
        logger.info("Shutting down all processes")
        self._shutdown = True

        # Stop health check
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Stop all processes
        tasks = [
            self.stop_person(name)
            for name in list(self.processes.keys())
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("All processes shut down")

    async def send_request(
        self,
        person_name: str,
        method: str,
        params: dict,
        timeout: float = 60.0
    ) -> dict:
        """
        Send IPC request to a Person process.

        Args:
            person_name: Target person name
            method: Method name
            params: Request parameters
            timeout: Timeout in seconds

        Returns:
            Response result dict

        Raises:
            KeyError: If person not found
            RuntimeError: If process not running
            ValueError: If response contains error
        """
        handle = self.processes.get(person_name)
        if not handle:
            raise KeyError(f"Person not found: {person_name}")

        response = await handle.send_request(method, params, timeout)

        if response.error:
            raise ValueError(
                f"Request failed: {response.error.get('message', 'Unknown error')}"
            )

        return response.result or {}

    async def send_request_stream(
        self,
        person_name: str,
        method: str,
        params: dict,
        timeout: float = 120.0
    ) -> AsyncIterator[IPCResponse]:
        """
        Send IPC request to a Person process and yield streaming responses.

        Args:
            person_name: Target person name
            method: Method name
            params: Request parameters (should include stream=True)
            timeout: Timeout in seconds for the entire stream

        Yields:
            IPCResponse objects (chunks and final result)

        Raises:
            KeyError: If person not found
            RuntimeError: If process not running
        """
        handle = self.processes.get(person_name)
        if not handle:
            raise KeyError(f"Person not found: {person_name}")

        async for response in handle.send_request_stream(
            method, params, timeout
        ):
            if response.error:
                raise ValueError(
                    f"Stream error: {response.error.get('message', 'Unknown error')}"
                )
            yield response

    async def _health_check_loop(self) -> None:
        """
        Health check loop.

        Periodically pings all processes and handles failures.
        """
        logger.info("Health check loop started")

        while not self._shutdown:
            try:
                await asyncio.sleep(self.health_config.ping_interval_sec)

                # Check all processes in parallel
                checks = [
                    self._check_process_health(person_name, handle)
                    for person_name, handle in list(self.processes.items())
                ]
                await asyncio.gather(*checks, return_exceptions=True)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")

        logger.info("Health check loop stopped")

    async def _check_process_health(
        self,
        person_name: str,
        handle: ProcessHandle
    ) -> None:
        """Check health of a single process."""
        # Skip if currently streaming (IPC lock held, ping would block)
        if handle._streaming:
            logger.debug(f"Skipping health check for {person_name} (streaming)")
            return

        # Skip if in startup grace period
        uptime = (datetime.now() - handle.stats.started_at).total_seconds()
        if uptime < self.health_config.startup_grace_sec:
            logger.debug(f"Skipping health check for {person_name} (startup grace)")
            return

        # Reset restart counter after stable uptime
        if uptime > self.restart_policy.reset_after_sec:
            if self._restart_counts.get(person_name, 0) > 0:
                self._restart_counts[person_name] = 0
                logger.info(
                    f"Restart counter reset for {person_name} "
                    f"(stable for {uptime:.0f}s)"
                )

        # Check if process is alive
        if not handle.is_alive():
            logger.error(
                f"Process exited unexpectedly: {person_name} "
                f"(exit_code={handle.stats.exit_code})"
            )
            asyncio.create_task(self._handle_process_failure(person_name, handle))
            return

        # Ping process
        success = await handle.ping(timeout=self.health_config.ping_timeout_sec)

        if success:
            # Ping successful
            if handle.stats.missed_pings > 0:
                logger.info(f"Process recovered: {person_name}")
            return

        # Ping failed
        logger.warning(
            f"Health check failed: {person_name} "
            f"(missed={handle.stats.missed_pings}/{self.health_config.max_missed_pings})"
        )

        # Check if hang threshold exceeded
        if handle.stats.missed_pings >= self.health_config.max_missed_pings:
            logger.error(
                f"Process hang detected: {person_name} "
                f"(PID {handle.get_pid()})"
            )
            asyncio.create_task(self._handle_process_hang(person_name, handle))

    async def _handle_process_failure(
        self,
        person_name: str,
        handle: ProcessHandle
    ) -> None:
        """Handle process exit/crash.

        Runs as an independent task so the health-check loop is not blocked
        by backoff sleeps.  A per-person guard prevents duplicate restarts.
        """
        if person_name in self._restarting:
            return
        self._restarting.add(person_name)

        try:
            # Check restart count (supervisor-level, survives handle recreation)
            count = self._restart_counts.get(person_name, 0)
            if count >= self.restart_policy.max_retries:
                logger.error(
                    f"Max restart retries exceeded for {person_name}. "
                    f"Manual intervention required."
                )
                handle.state = ProcessState.FAILED
                return

            # Calculate backoff delay
            backoff = min(
                self.restart_policy.backoff_base_sec * (2 ** count),
                self.restart_policy.backoff_max_sec
            )

            logger.info(
                f"Scheduling restart for {person_name} "
                f"(retry {count + 1}/{self.restart_policy.max_retries}, "
                f"delay={backoff:.1f}s)"
            )

            # Wait and restart
            await asyncio.sleep(backoff)

            self._restart_counts[person_name] = count + 1
            await self.restart_person(person_name)

            logger.info(
                f"Process restarted: {person_name} "
                f"(PID {self.processes[person_name].get_pid()}, "
                f"retry={count + 1}/{self.restart_policy.max_retries})"
            )

        except Exception as e:
            logger.error(f"Failed to restart {person_name}: {e}")
            handle.state = ProcessState.FAILED
        finally:
            self._restarting.discard(person_name)

    async def _handle_process_hang(
        self,
        person_name: str,
        handle: ProcessHandle
    ) -> None:
        """Handle hung process (kill and restart)."""
        logger.warning(f"Killing hung process: {person_name}")

        # Kill process
        await handle.kill()

        # Restart
        await self._handle_process_failure(person_name, handle)

    def get_process_status(self, person_name: str) -> dict:
        """
        Get status of a Person process.

        Returns:
            Status dict with state, PID, uptime, etc.
        """
        handle = self.processes.get(person_name)
        if not handle:
            return {"status": "not_found"}

        uptime = (datetime.now() - handle.stats.started_at).total_seconds()

        return {
            "status": handle.state.value,
            "pid": handle.get_pid(),
            "uptime_sec": uptime,
            "restart_count": self._restart_counts.get(person_name, 0),
            "missed_pings": handle.stats.missed_pings,
            "last_ping_at": (
                handle.stats.last_ping_at.isoformat()
                if handle.stats.last_ping_at else None
            )
        }

    def get_all_status(self) -> dict[str, dict]:
        """Get status of all processes."""
        return {
            name: self.get_process_status(name)
            for name in self.processes
        }
