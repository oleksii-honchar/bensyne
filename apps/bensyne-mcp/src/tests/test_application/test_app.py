"""Tests for application factory and main entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestCreateApplication:
    """Test that create_application wires all components correctly."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_router(self) -> MagicMock:
        router = MagicMock()
        router.get_active_instances.return_value = 1
        router.get_active_banks.return_value = {"default"}
        return router

    @pytest.fixture
    def mock_memory_bank_service(self) -> MagicMock:
        return MagicMock()

    def test_create_application_returns_mcp_server(self, mock_config, mock_router, mock_memory_bank_service) -> None:
        """create_application returns a FastMCP instance."""
        with (
            patch("src.app.create_server") as mock_create_server,
            patch("src.app.register_tools"),
            patch("src.app.mount_health_routes"),
        ):

            mock_mcp = MagicMock()
            mock_create_server.return_value = mock_mcp

            from src.app import create_application

            result = create_application(mock_config, mock_router, mock_memory_bank_service)

            assert result is mock_mcp

    def test_create_application_calls_create_server_with_config(self, mock_config, mock_router, mock_memory_bank_service) -> None:
        """create_application passes config to create_server."""
        with (
            patch("src.app.create_server") as mock_create_server,
            patch("src.app.register_tools"),
            patch("src.app.mount_health_routes"),
        ):

            mock_mcp = MagicMock()
            mock_create_server.return_value = mock_mcp

            from src.app import create_application

            create_application(mock_config, mock_router, mock_memory_bank_service)

            mock_create_server.assert_called_once_with(mock_config)

    def test_create_application_registers_tools(self, mock_config, mock_router, mock_memory_bank_service) -> None:
        """create_application registers MCP tools with the router injected (container defaults to None)."""
        with (
            patch("src.app.create_server") as mock_create_server,
            patch("src.app.register_tools") as mock_register_tools,
            patch("src.app.mount_health_routes"),
        ):

            mock_mcp = MagicMock()
            mock_create_server.return_value = mock_mcp

            from src.app import create_application

            create_application(mock_config, mock_router, mock_memory_bank_service)

            mock_register_tools.assert_called_once_with(mock_mcp, mock_router, mock_memory_bank_service, None)

    def test_create_application_plumbs_container_to_register_tools(self, mock_config, mock_router, mock_memory_bank_service) -> None:
        """create_application passes the DI container through to register_tools (D25)."""
        with (
            patch("src.app.create_server") as mock_create_server,
            patch("src.app.register_tools") as mock_register_tools,
            patch("src.app.mount_health_routes"),
        ):

            mock_mcp = MagicMock()
            mock_create_server.return_value = mock_mcp
            mock_container = MagicMock()

            from src.app import create_application

            create_application(mock_config, mock_router, mock_memory_bank_service, mock_container)

            mock_register_tools.assert_called_once_with(mock_mcp, mock_router, mock_memory_bank_service, mock_container)

    def test_create_application_mounts_health_routes(self, mock_config, mock_router, mock_memory_bank_service) -> None:
        """create_application mounts health check endpoints."""
        with (
            patch("src.app.create_server") as mock_create_server,
            patch("src.app.register_tools"),
            patch("src.app.mount_health_routes") as mock_mount_health,
        ):

            mock_mcp = MagicMock()
            mock_create_server.return_value = mock_mcp

            from src.app import create_application

            create_application(mock_config, mock_router, mock_memory_bank_service)

            mock_mount_health.assert_called_once_with(mock_mcp, mock_router)


class TestRegisterTools:
    """Test that register_tools wires all MCP tool handlers."""

    def test_register_tools_registers_all_tools(self) -> None:
        """register_tools registers all expected tool names."""
        from src.infrastructure.bank.router import MemoryBankRouter
        from src.infrastructure.mcp import handlers

        mock_mcp = MagicMock()
        mock_router = MagicMock(spec=MemoryBankRouter)
        mock_service = MagicMock()

        from src.app import register_tools

        register_tools(mock_mcp, mock_router, mock_service)

        # Verify tool registration calls — each tool should be registered
        # Check that mcp.tool was called for each handler
        assert mock_mcp.tool.call_count >= 7  # remember, recall, forget, update, sleep, stats + list_banks + search_memory_bank


class TestListRegisterToolClosures:
    """listMemoryBanks / registerMemoryBank closures invoke the service-backed handlers.

    Task 7: create_application(..., memory_bank_service, ...) must plumb the service
    into the list/register handlers (router param stays — same injection pattern).
    """

    def _capture_tool_fn(self, mock_mcp: MagicMock, tool_name: str):
        # With the @mcp.tool(name=...) decorator pattern, the name is passed to
        # mcp.tool and the function is applied by the returned decorator — the
        # two calls are 1:1 in order.
        for i, call in enumerate(mock_mcp.tool.call_args_list):
            if call.kwargs.get("name") == tool_name:
                return mock_mcp.tool.return_value.call_args_list[i].args[0]
        raise AssertionError(f"tool {tool_name} not registered")

    def test_list_banks_closure_invokes_service_backed_handler(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock, patch

        mock_mcp = MagicMock()
        mock_router = MagicMock()
        mock_service = MagicMock()

        from src.app import register_tools

        with patch(
            "src.infrastructure.mcp.handlers.handle_list_banks",
            new=AsyncMock(return_value={"banks": []}),
        ) as mock_handle:
            register_tools(mock_mcp, mock_router, mock_service)
            tool_fn = self._capture_tool_fn(mock_mcp, "listMemoryBanks")
            result = asyncio.run(tool_fn())

        assert result == {"banks": []}
        mock_handle.assert_awaited_once_with(mock_router, mock_service, {})

    def test_register_bank_closure_invokes_service_backed_handler(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock, patch

        mock_mcp = MagicMock()
        mock_router = MagicMock()
        mock_service = MagicMock()

        from src.app import register_tools

        with patch(
            "src.infrastructure.mcp.handlers.handle_register_bank",
            new=AsyncMock(return_value={"status": "registered", "name": "ns"}),
        ) as mock_handle:
            register_tools(mock_mcp, mock_router, mock_service)
            tool_fn = self._capture_tool_fn(mock_mcp, "registerMemoryBank")
            result = asyncio.run(tool_fn("ns", "desc"))

        assert result == {"status": "registered", "name": "ns"}
        mock_handle.assert_awaited_once_with(
            mock_router, mock_service, {"name": "ns", "description": "desc"}
        )

    def test_search_memory_bank_closure_invokes_service_backed_handler(self) -> None:
        """searchMemoryBank closure forwards (query, limit, agent_id) into the handler
        so the discovery primitive is wired through the same service-backed pattern
        as listMemoryBanks / registerMemoryBank."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        mock_mcp = MagicMock()
        mock_router = MagicMock()
        mock_service = MagicMock()

        from src.app import register_tools

        with patch(
            "src.infrastructure.mcp.handlers.handle_search_memory_bank",
            new=AsyncMock(return_value={"matches": [], "total": 0}),
        ) as mock_handle:
            register_tools(mock_mcp, mock_router, mock_service)
            tool_fn = self._capture_tool_fn(mock_mcp, "searchMemoryBank")
            result = asyncio.run(tool_fn("reviewer", 5, "reviewer"))

        assert result == {"matches": [], "total": 0}
        mock_handle.assert_awaited_once_with(
            mock_router,
            mock_service,
            {"query": "reviewer", "limit": 5, "agent_id": "reviewer"},
        )


class TestMountHealthRoutes:
    """Test that mount_health_routes wires health endpoints."""

    def test_mount_health_routes_sets_router_on_health_module(self) -> None:
        """mount_health_routes registers the router for health endpoint queries."""
        mock_mcp = MagicMock()
        mock_router = MagicMock()

        with patch("src.middleware.health.set_memory_bank_router") as mock_set_router:
            from src.app import mount_health_routes

            mount_health_routes(mock_mcp, mock_router)

            mock_set_router.assert_called_once_with(mock_router)


class TestMainEntryPoints:
    """Test main.py CLI argument parsing and startup sequence."""

    def test_main_parses_cli_args(self, monkeypatch) -> None:
        """main.py parses --port, --data-dir, --log-level arguments."""
        import sys
        from unittest.mock import patch

        # main() surfaces --data-dir through the DATA_DIR env channel for the
        # repository singleton — restore afterwards so it doesn't leak.
        monkeypatch.setenv("DATA_DIR", "TEST_DATADIR_SENTINEL")

        test_args = ["main.py", "--port", "8080", "--data-dir", "/tmp/data", "--log-level", "DEBUG"]

        # Track replaced config values
        replaced_configs = []

        def mock_replace(obj, **kwargs):
            replaced_configs.append((obj, kwargs))
            return obj

        # Patch at source module level so reload picks up mocks
        with (
            patch.object(sys, "argv", test_args),
            patch("src.infrastructure.config.manager.ConfigManager") as MockConfigManager,
            patch("src.utils.logging.setup_logging") as mock_setup_logging,
            patch("src.infrastructure.bank.router.MemoryBankRouter") as MockMemoryBankRouter,
            patch("src.infrastructure.di.ProductionContainer") as MockProductionContainer,
            patch("src.app.create_application") as mock_create_app,
            patch("src.middleware.health.mark_default_instance_ready"),
            patch("asyncio.get_event_loop") as mock_get_loop,
            patch("dataclasses.replace", side_effect=mock_replace),
        ):

            mock_config = MagicMock()
            mock_config.server.port = 3000
            mock_config.server.host = "0.0.0.0"
            mock_config.logging.level = "INFO"
            mock_config.instance_pool.data_dir = "/data"
            mock_config.instance_pool.default_bank = "default"
            mock_config.instance_pool.max_instances = 50

            MockConfigManager.return_value.load.return_value = mock_config
            mock_setup_logging.return_value = MagicMock()

            mock_router_instance = MagicMock()
            MockMemoryBankRouter.return_value = mock_router_instance

            mock_container = MagicMock()
            MockProductionContainer.return_value = mock_container

            mock_app = MagicMock()
            mock_create_app.return_value = mock_app

            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop

            # Import after patching sys.argv and source modules
            import importlib
            import main

            importlib.reload(main)

            try:
                main.main()
            except SystemExit:
                pass  # Expected after signal handler setup

            # Verify CLI overrides were applied via dataclasses.replace
            # Check that port=8080 was passed
            port_replaces = [kwargs for obj, kwargs in replaced_configs if "port" in kwargs]
            assert any(kwargs.get("port") == 8080 for kwargs in port_replaces)

            # Check that data_dir="/tmp/data" was passed
            dir_replaces = [kwargs for obj, kwargs in replaced_configs if "data_dir" in kwargs]
            assert any(kwargs.get("data_dir") == "/tmp/data" for kwargs in dir_replaces)

            # Check that level="DEBUG" was passed
            level_replaces = [kwargs for obj, kwargs in replaced_configs if "level" in kwargs]
            assert any(kwargs.get("level") == "DEBUG" for kwargs in level_replaces)

    def test_main_startup_sequence_order(self) -> None:
        """main.py follows correct startup sequence: config → container →
        ensure_default_bank → create_application (service + container passed)."""
        import sys
        from unittest.mock import patch, MagicMock

        test_args = ["main.py"]

        # Use dataclasses.replace-compatible mock config
        mock_server = MagicMock()
        mock_server.port = 3000
        mock_server.host = "0.0.0.0"

        mock_logging_cfg = MagicMock()
        mock_logging_cfg.level = "INFO"
        mock_logging_cfg.format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        mock_logging_cfg.log_file = None

        mock_instance_pool = MagicMock()
        mock_instance_pool.data_dir = "/tmp/test-data"
        mock_instance_pool.default_bank = "default"
        mock_instance_pool.max_instances = 50
        mock_instance_pool.eviction_timeout = 300

        mock_config = MagicMock()
        mock_config.server = mock_server
        mock_config.logging = mock_logging_cfg
        mock_config.instance_pool = mock_instance_pool

        # Patch at source module level so reload picks up mocks
        with (
            patch.object(sys, "argv", test_args),
            patch("src.infrastructure.config.manager.ConfigManager") as MockConfigManager,
            patch("src.utils.logging.setup_logging") as mock_setup_logging,
            patch("src.infrastructure.bank.router.MemoryBankRouter") as MockMemoryBankRouter,
            patch("src.infrastructure.di.ProductionContainer") as MockProductionContainer,
            patch("src.app.create_application") as mock_create_app,
            patch("src.middleware.health.mark_default_instance_ready") as mock_mark_ready,
            patch("asyncio.get_event_loop") as mock_get_loop,
            patch("dataclasses.replace", side_effect=lambda obj, **kwargs: obj),
        ):

            MockConfigManager.return_value.load.return_value = mock_config
            mock_setup_logging.return_value = MagicMock()

            mock_router_instance = MagicMock()
            MockMemoryBankRouter.return_value = mock_router_instance

            # Container mock: service resolved once, seed recorded before app creation.
            boot_order: list[str] = []
            mock_service = MagicMock()
            mock_service.ensure_default_bank.side_effect = lambda desc: boot_order.append(
                "ensure_default_bank"
            )
            mock_container = MagicMock()
            mock_container.memory_bank_service.return_value = mock_service
            MockProductionContainer.return_value = mock_container

            mock_app = MagicMock()
            mock_create_app.return_value = mock_app
            mock_create_app.side_effect = lambda *a, **kw: boot_order.append(
                "create_application"
            ) or mock_app

            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop

            import importlib
            import main

            importlib.reload(main)

            try:
                main.main()
            except SystemExit:
                pass

            # Verify startup sequence was called in order
            assert MockConfigManager.called
            assert mock_setup_logging.called
            assert MockMemoryBankRouter.called
            assert MockProductionContainer.called
            assert mock_service.ensure_default_bank.called
            assert mock_mark_ready.called
            assert boot_order == ["ensure_default_bank", "create_application"]

            # New signature: create_application(config, router, service, container)
            mock_create_app.assert_called_once_with(
                mock_config, mock_router_instance, mock_service, mock_container
            )

    def test_main_boot_seeds_default_bank(self, tmp_path, monkeypatch) -> None:
        """Boot with a temp DATA_DIR seeds memory_banks.db with a 'default' row.

        Config → container → ensure_default_bank → create_application executes
        without import errors; the real app data dir stays untouched.
        """
        import sys
        from unittest.mock import patch, MagicMock

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        test_args = ["main.py"]

        mock_server = MagicMock()
        mock_server.port = 3000
        mock_server.host = "0.0.0.0"

        mock_logging_cfg = MagicMock()
        mock_logging_cfg.level = "INFO"
        mock_logging_cfg.format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        mock_logging_cfg.log_file = None

        mock_instance_pool = MagicMock()
        mock_instance_pool.data_dir = str(tmp_path)
        mock_instance_pool.default_bank = "default"
        mock_instance_pool.max_instances = 50
        mock_instance_pool.eviction_timeout = 300

        mock_config = MagicMock()
        mock_config.server = mock_server
        mock_config.logging = mock_logging_cfg
        mock_config.instance_pool = mock_instance_pool

        with (
            patch.object(sys, "argv", test_args),
            patch("src.infrastructure.config.manager.ConfigManager") as MockConfigManager,
            patch("src.utils.logging.setup_logging") as mock_setup_logging,
            patch("src.infrastructure.bank.router.MemoryBankRouter") as MockMemoryBankRouter,
            patch("src.app.create_application") as mock_create_app,
            patch("src.middleware.health.mark_default_instance_ready"),
            patch("asyncio.get_event_loop") as mock_get_loop,
            patch("dataclasses.replace", side_effect=lambda obj, **kwargs: obj),
        ):

            MockConfigManager.return_value.load.return_value = mock_config
            mock_setup_logging.return_value = MagicMock()

            mock_router_instance = MagicMock()
            MockMemoryBankRouter.return_value = mock_router_instance

            mock_app = MagicMock()
            mock_create_app.return_value = mock_app

            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop

            import importlib
            import main

            importlib.reload(main)

            try:
                main.main()
            except SystemExit:
                pass

            # Real ProductionContainer + real service ran the seed against the
            # temp DATA_DIR — memory_banks.db exists with a default row.
            from src.infrastructure.bank.memory_bank_repository import (
                MemoryBankRepository,
                memory_banks_db_path,
            )

            db_path = memory_banks_db_path(tmp_path)
            assert db_path.exists()

            repo = MemoryBankRepository(db_path)
            bank = repo.find_by_id("default").value
            assert bank is not None
            assert bank.name == "default"

            # create_application received the resolved service singleton + container.
            service = mock_create_app.call_args.args[2]
            container = mock_create_app.call_args.args[3]
            from src.application.services.memory_bank_service import MemoryBankService

            assert isinstance(service, MemoryBankService)
            assert container.memory_bank_service() is service

    def test_main_data_dir_flag_governs_repository_singleton(self, tmp_path, monkeypatch) -> None:
        """--data-dir CLI flag must route the repository singleton's memory_banks.db
        into that dir — not the CWD-relative ./data default.

        Task 8 wired the real repository via ``resolve_data_dir()`` (env/./data);
        ``--data-dir`` previously patched only the router config, so a live server
        with ``--data-dir <tmp>`` wrote memory_banks.db into the real app data dir.
        """
        import sys
        from unittest.mock import patch, MagicMock

        # Ensure no DATA_DIR env leak — the flag alone must win.
        monkeypatch.setenv("DATA_DIR", "TEST_DATADIR_SENTINEL")
        test_args = ["main.py", "--data-dir", str(tmp_path)]

        mock_server = MagicMock()
        mock_server.port = 3000
        mock_server.host = "0.0.0.0"

        mock_logging_cfg = MagicMock()
        mock_logging_cfg.level = "INFO"
        mock_logging_cfg.format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        mock_logging_cfg.log_file = None

        mock_instance_pool = MagicMock()
        mock_instance_pool.data_dir = "./data"
        mock_instance_pool.default_bank = "default"
        mock_instance_pool.max_instances = 50
        mock_instance_pool.eviction_timeout = 300

        mock_config = MagicMock()
        mock_config.server = mock_server
        mock_config.logging = mock_logging_cfg
        mock_config.instance_pool = mock_instance_pool

        with (
            patch.object(sys, "argv", test_args),
            patch("src.infrastructure.config.manager.ConfigManager") as MockConfigManager,
            patch("src.utils.logging.setup_logging") as mock_setup_logging,
            patch("src.infrastructure.bank.router.MemoryBankRouter") as MockMemoryBankRouter,
            patch("src.app.create_application") as mock_create_app,
            patch("src.middleware.health.mark_default_instance_ready"),
            patch("asyncio.get_event_loop") as mock_get_loop,
            patch("dataclasses.replace", side_effect=lambda obj, **kwargs: obj),
        ):

            MockConfigManager.return_value.load.return_value = mock_config
            mock_setup_logging.return_value = MagicMock()

            mock_router_instance = MagicMock()
            MockMemoryBankRouter.return_value = mock_router_instance

            mock_app = MagicMock()
            mock_create_app.return_value = mock_app

            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop

            import importlib
            import main

            importlib.reload(main)

            try:
                main.main()
            except SystemExit:
                pass

            # Real ProductionContainer ran the seed — memory_banks.db must land
            # under the --data-dir target, never the CWD-relative ./data default.
            from src.infrastructure.bank.memory_bank_repository import memory_banks_db_path

            assert memory_banks_db_path(tmp_path).exists()
            assert not memory_banks_db_path("./data").exists()


class TestGracefulShutdown:
    """Test graceful shutdown on SIGINT/SIGTERM."""

    def test_shutdown_handler_logs_and_exits(self) -> None:
        """shutdown_handler logs cleanup and exits cleanly."""
        import asyncio
        import logging
        from unittest.mock import MagicMock, patch

        mock_router = MagicMock()
        mock_router.instances = {"default": MagicMock(), "tenant1": MagicMock()}

        with patch("sys.exit") as mock_exit:
            import importlib
            import main

            importlib.reload(main)

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(main.shutdown_handler(signal.SIGINT, mock_router))
            finally:
                loop.close()

            mock_exit.assert_called_once_with(0)


class TestApplicationIntegration:
    """Integration test: app starts and health endpoint responds."""

    def test_app_integration_health_endpoint(self) -> None:
        """Full app creation with mocked dependencies allows health check."""
        from src.middleware.health import create_health_app, mark_default_instance_ready, set_memory_bank_router
        from starlette.testclient import TestClient

        # Reset health state
        import src.middleware.health as health_module

        health_module._default_instance_ready = False
        health_module._memory_bank_router = None

        # Create mock router — methods must return proper types
        mock_router = MagicMock()
        mock_router.get_active_instances.return_value = 1
        mock_router.get_active_banks.return_value = {"default"}

        # Set up health app with router
        health_app = create_health_app()
        set_memory_bank_router(mock_router)
        mark_default_instance_ready()

        client = TestClient(health_app)

        # Test /health returns expected data
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["instances"] == 1
        assert "default" in data["banks"]

        # Test /health/ready returns 200
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"

        # Test /health/log returns log info
        response = client.get("/health/log")
        assert response.status_code == 200
        assert "log_level" in response.json()
        assert "recent_logs" in response.json()


# Import signal for shutdown test
import signal
