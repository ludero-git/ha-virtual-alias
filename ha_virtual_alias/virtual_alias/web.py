import logging
import threading
import ipaddress
from collections import deque
from pathlib import Path

from flask import Flask, jsonify, send_from_directory, request
from werkzeug.serving import make_server

from .api import RestAPI
from .const import WEB_HOST, WEB_PORT

LOGGER = logging.getLogger(__name__)

PUBLIC_DIR = Path(__file__).resolve().parent / "public"

LOG_FORMAT = "%(asctime)s %(levelname)s " "%(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class LogBufferHandler(logging.Handler):
    def __init__(self, max_lines):
        super().__init__()

        self.lines = deque(maxlen=max_lines)

        self.setFormatter(
            logging.Formatter(
                LOG_FORMAT,
                datefmt=LOG_DATE_FORMAT,
            )
        )

    def emit(self, record):
        try:
            message = self.format(record)

            for line in message.splitlines():
                self.lines.append(line)

        except Exception:
            self.handleError(record)

    def get_lines(self):
        self.acquire()

        try:
            return list(self.lines)

        finally:
            self.release()


# Filter that excludes werkzeug (API requests) logs.
class ExcludeWerkzeugFilter(logging.Filter):
    def filter(self, record):
        return not record.name.startswith("werkzeug")


def install_log_handler(handler):
    root_logger = logging.getLogger()

    if handler not in root_logger.handlers:
        root_logger.addHandler(handler)


class Web:
    def __init__(
        self,
        app,
        web_config,
        host=WEB_HOST,
        port=WEB_PORT,
    ):
        self.core = app
        self.config = web_config
        self.host = host
        self.port = port

        self.server = None
        self.thread = None

        self.info = {
            "version": None,
            "architecture": None,
        }

        self.log_handler = LogBufferHandler(web_config.log_lines)
        self.log_handler.addFilter(ExcludeWerkzeugFilter())

        install_log_handler(self.log_handler)

        self.app = Flask(
            __name__,
            static_folder=None,
        )

        self._register_routes()

    def _register_routes(self):
        @self.app.get("/api/devices")
        def devices():
            return jsonify(self.core.get_devices())

        @self.app.get("/api/logs")
        def logs():
            return jsonify(self.log_handler.get_lines())

        @self.app.get("/api/info")
        def info():
            return jsonify(self.info)

        @self.app.get("/api/find")
        async def find():
            query = request.args.get("query", "").lower().strip()

            if not query:
                return jsonify(mac=None, message="No query was provided.")

            try:
                ipaddress.ip_address(query)
                ip = query
            except ValueError:
                ip = await self.core.discovery._lookup_ip_for_hostname(query)

            if not ip:
                return jsonify(mac=None, message="Failed to lookup or extract IP.")

            mac = await self.core.discovery._lookup_mac_for_ip(ip)

            return jsonify(
                mac=mac,
                message=None if mac else "Failed to lookup MAC.",
            )

        @self.app.get("/")
        def index():
            return send_from_directory(
                PUBLIC_DIR,
                "index.html",
            )

        @self.app.get("/<path:path>")
        def public_file(path):
            return send_from_directory(
                PUBLIC_DIR,
                path,
            )

    async def _load_info(self):
        try:
            async with RestAPI() as api:
                addon_info = await api.get("/addons/self/info")

                supervisor_info = await api.get("/info")

            architecture = supervisor_info.get("arch")

            self.info = {
                "version": addon_info.get("version"),
                "architecture": (architecture.lower() if architecture else None),
            }

        except Exception:
            LOGGER.exception("Failed to load app information")

    async def start(self):
        LOGGER.info("Starting web server")

        await self._load_info()

        self.server = make_server(
            self.host,
            self.port,
            self.app,
            threaded=True,
        )

        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="web",
            daemon=True,
        )

        self.thread.start()

        LOGGER.info(
            "Web server started on %s:%s",
            self.host,
            self.port,
        )

    async def stop(self):
        if self.server is None:
            return

        LOGGER.info("Stopping web server")

        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

        logging.getLogger().removeHandler(self.log_handler)

        self.server = None
        self.thread = None

        LOGGER.info("Web server stopped")
