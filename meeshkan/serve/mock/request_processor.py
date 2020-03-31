import json
import logging
import random
from typing import Sequence

from http_types import Request, Response
from openapi_typed_2 import OpenAPIObject

from meeshkan.serve.mock.callbacks import CallbackManager
from meeshkan.serve.mock.faker import DefaultFaker
from meeshkan.serve.mock.faker.faker_exception import FakerException
from meeshkan.serve.mock.matcher import match_request_to_openapi
from meeshkan.serve.mock.rest import RestMiddlewareManager
from meeshkan.serve.mock.security import match_to_security_schemes
from meeshkan.serve.mock.specs import OpenAPISpecification
from meeshkan.serve.mock.storage.manager import StorageManager
from meeshkan.serve.mock.storage.mock_data import MockData

logger = logging.getLogger(__name__)


class RequestProcessor:
    _specs: Sequence[OpenAPISpecification]

    def __init__(
        self,
        specs: Sequence[OpenAPISpecification],
        storage_manager: StorageManager,
        callback_manager: CallbackManager,
        rest_middleware_manager: RestMiddlewareManager,
    ):
        self._specs = specs
        self._storage_manager = storage_manager
        self._callback_manager = callback_manager
        self._rest_middleware_manager = rest_middleware_manager
        self._faker = DefaultFaker()

        for spec in specs:
            self._storage_manager.add_mock(spec.source, spec.api)

    def match_error(self, msg: str, req: Request):
        json_resp = {
            "message": "%s. Here is the full request: host=%s, path=%s, method=%s."
            % (msg, req.host, req.path, req.method.value)
        }
        return Response(
            statusCode=501,
            body=json.dumps(json_resp),
            bodyAsJson=json_resp,
            headers={},
            timestamp=None,
        )

    def _match_response(self, spec: OpenAPIObject, storage: MockData, request: Request):
        try:
            return self._faker.process(spec, storage, request)
        except FakerException as e:
            return self.match_error(str(e), request)

    def process(self, request: Request) -> Response:
        if request.method.value is None:
            method_error = "Could not find a method %s for path %s on hostname %s." % (
                request.method.value,
                request.path,
                request.host,
            )
            return self.match_error(method_error, request)

        specs = self._rest_middleware_manager.spew(request, self._specs)

        logger.debug("Matching to security schemes of %d specs", len(specs))
        maybe_security_response = match_to_security_schemes(
            request, [spec.api for spec in specs]
        )

        if maybe_security_response is not None:
            logger.debug("Matched to security scheme, returning response.")
            return maybe_security_response

        match = match_request_to_openapi(request, specs)

        if len(match) == 0:
            return self._callback_manager(
                request,
                self.match_error(
                    "Could not find an open API schema for the host %s." % request.host,
                    request,
                ),
                self._storage_manager.default,
            )

        spec = random.choice(match)
        if spec.api.paths is None or len(spec.api.paths.items()) == 0:
            path_error = "Could not find a path %s on hostname %s." % (
                request.path,
                request.host,
            )
            return self.match_error(path_error, request)

        storage = self._storage_manager[spec.source]
        response = self._match_response(spec.api, storage, request)
        return self._callback_manager(request, response, storage)