import logging
import os

import click
import tornado.ioloop
import yaml
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.web import Application

from .admin.views import StorageView
from .proxy.proxy import RecordProxy
from .server.callbacks import callback_manager
from .server.mocking_service import MockingService
from .server.response_matcher import ResponseMatcher
from .server.views import MockServerView
from .utils.data_callback import RequestLoggingCallback

LOG_CONFIG = os.path.join(os.path.dirname(__file__), 'logging.yaml')
logger = logging.getLogger(__name__)

def start_admin(port):
    app = Application([
        (r'/admin/storage', StorageView)
    ])
    http_server = HTTPServer(app)
    http_server.listen(port)
    logger.info('Starting admin endpont on http://localhost:%s/admin', port)



@click.command()
@click.option('--port', default="8000", help='Server port')
@click.option('--admin_port', default="8888", help='Admin server port')
@click.option('--log_dir', default="./logs", help='API calls logs direcotry')
@click.option('--schema_dir', default="./__unmock__", help='Directory with OpenAPI schemas')
def record(port, admin_port, log_dir, schema_dir):
    start_admin(admin_port)
    logger.info('Starting Meeshkan proxy in recording mode on http://localhost:%s', port)
    with RequestLoggingCallback(recording=True, log_dir=log_dir, schema_dir=schema_dir) as callback:
        server = RecordProxy(callback)
        server.listen(port)
        tornado.ioloop.IOLoop.instance().start()

class MeeshkanApplication(Application):
    mocking_service: MockingService

def make_mocking_app(callback_path, schema_dir):
    app = MeeshkanApplication([
        (r'/.*', MockServerView)
    ])
    callback_manager.load(callback_path)

    matcher = ResponseMatcher(schema_dir)

    app.mocking_service = MockingService(matcher)
    return app

@click.command()
@click.option('--callback_path', default="./callbacks", help='Directory with configured callbacks')
@click.option('--admin_port', default="8888", help='Admin server port')
@click.option('--port', default="8000", help='Server port')
@click.option('-s', '--schema_dir', default="./__unmock__", help='Directory with OpenAPI schemas')
def mock(port, admin_port, schema_dir, callback_path):
    start_admin(admin_port)
    app = make_mocking_app(callback_path, schema_dir)
    http_server = HTTPServer(app)
    http_server.listen(port)
    logger.info('Mock server is listening on http://localhost:%s', port)
    IOLoop.current().start()
