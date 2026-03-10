#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Webhook сервер для GitHub деплоя CRM.
При push в ветку main: cd /root/crm, git pull, systemctl restart crm.
Порт: WEBHOOK_PORT (по умолчанию 3001). Endpoints: GET /health, POST /webhook.
"""
import json
import logging
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse
import hmac
import hashlib

# Настройки
PORT = int(os.getenv('WEBHOOK_PORT', '3001'))
SECRET_TOKEN = os.getenv('GITHUB_WEBHOOK_SECRET', '')
PROJECT_DIR = Path(__file__).resolve().parent
LOG_FILE = PROJECT_DIR / 'data' / 'webhook.log'

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class WebhookHandler(BaseHTTPRequestHandler):
    def _send_response(self, status: int, message: str):
        response = json.dumps({"message": message}, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def _verify_signature(self, payload: bytes, signature: str) -> bool:
        if not SECRET_TOKEN:
            logger.warning("GITHUB_WEBHOOK_SECRET не установлен, пропускаем проверку")
            return True
        expected = f"sha256={hmac.new(SECRET_TOKEN.encode('utf-8'), payload, hashlib.sha256).hexdigest()}"
        return hmac.compare_digest(signature, expected)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/health':
            self._send_response(200, "Webhook server is running")
        else:
            self._send_response(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != '/webhook':
            self._send_response(404, "Not found")
            return

        content_type = self.headers.get('Content-Type', '')
        signature = self.headers.get('X-Hub-Signature-256', '')
        event_type = self.headers.get('X-GitHub-Event', '')

        if 'application/json' not in content_type:
            self._send_response(400, "Invalid Content-Type")
            return

        try:
            content_length = int(self.headers.get('Content-Length') or 0)
        except (TypeError, ValueError):
            content_length = 0
        if content_length <= 0:
            self._send_response(400, "Empty request body")
            return

        payload = self.rfile.read(content_length)

        if not self._verify_signature(payload, signature):
            logger.error("Неверная подпись webhook")
            self._send_response(403, "Invalid signature")
            return

        try:
            data = json.loads(payload.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"JSON error: {e}")
            self._send_response(400, "Invalid JSON")
            return

        logger.info(f"Webhook: {event_type} from {data.get('repository', {}).get('full_name', 'unknown')}")

        if event_type != 'push':
            self._send_response(200, f"Event {event_type} ignored")
            return

        ref = data.get('ref', '')
        if ref != 'refs/heads/main':
            logger.info(f"Игнорируем ветку: {ref}")
            self._send_response(200, f"Branch {ref} ignored")
            return

        try:
            self._deploy()
            self._send_response(200, "Deployment successful")
        except Exception as e:
            logger.error(f"Deploy error: {e}")
            self._send_response(500, f"Deployment failed: {str(e)}")

    def _deploy(self):
        """cd /root/crm && git pull && systemctl restart crm"""
        logger.info("Деплой CRM: git pull + restart crm...")
        if not PROJECT_DIR.exists():
            raise Exception(f"Директория не существует: {PROJECT_DIR}")

        r = subprocess.run(
            ['git', 'pull'],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(PROJECT_DIR)
        )
        if r.returncode != 0:
            logger.error(f"git pull: {r.stderr}")
            raise Exception(f"git pull failed: {r.stderr}")
        logger.info(f"git pull: {r.stdout}")

        subprocess.run(
            ['systemctl', 'restart', 'crm'],
            capture_output=True,
            timeout=15,
            cwd=str(PROJECT_DIR)
        )
        logger.info("systemctl restart crm выполнен")
        logger.info("Деплой CRM завершён")

    def log_message(self, format, *args):
        logger.info("%s", args[0] if args else format)


def run_server():
    server = HTTPServer(('0.0.0.0', PORT), WebhookHandler)
    logger.info(f"Webhook CRM на http://0.0.0.0:{PORT}, endpoint /webhook")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Сервер остановлен")
    finally:
        server.server_close()


if __name__ == '__main__':
    run_server()
