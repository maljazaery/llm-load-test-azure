import json
import logging
import time

import requests
import urllib3
from openai import RateLimitError

from plugins import plugin
from result import RequestResult
from openai import AzureOpenAI

urllib3.disable_warnings()
"""
Example plugin config.yaml:

plugin: "azure_oai_embedding_plugin"
plugin_options:
    url: "<YOUR ENDPOINT>"
    key: "<YOUR KEY>"
    deployment: "<YOUR DEPLOYMENT NAME>"
    api_version: "2024-02-01"
"""

required_args = ["url", "key", "deployment"]

logger = logging.getLogger("user")

# This plugin is written primarily for testing vLLM, though it can be made
# to work for other runtimes which conform to the OpenAI API, as required.
class AzureOpenAIEmbeddingPlugin(plugin.Plugin):
    def __init__(self, args):
        self._parse_args(args)

    def _parse_args(self, args):
        for arg in required_args:
            if arg not in args:
                logger.error("Missing plugin arg: %s", arg)

       
        self.request_func = self.request_http

        self.host = f"{args.get('url')}"
        self.key = args.get("key")
        self.model_name = args.get("deployment")
        if not args.get("api_version"):
            self.version = "2024-02-01"
        else:
            self.version = args.get("api_version")
        

    def request_http(self, query: dict, user_id: int, test_end_time: float = 0):

        result = RequestResult(user_id, query.get("text"), query.get("input_tokens"))

        result.start_time = time.time()

        client = AzureOpenAI(
                api_key=self.key,  
                api_version=self.version,
                azure_endpoint = self.host,
                max_retries=0
            )

        input = query.get("text")
        response = None
        try:
            response = client.embeddings.create(model=self.model_name, input=input)

        except RateLimitError as err:
            result.end_time = time.time()
            result.error_text = repr(err)
            if response is not None:
                result.error_code = response.status_code
            logger.error("RateLimitError error")
            return result
        except requests.exceptions.HTTPError as err:
            result.end_time = time.time()
            result.error_text = repr(err)
            if response is not None:
                result.error_code = response.status_code
            logger.error("HTTP error")
            return result

        result.end_time = time.time()
            
        try:
            message = response.model_dump_json()
            
            result.output_text = str(message)
            result.input_tokens = self.num_tokens_from_string(query.get("text"))
            result.output_tokens = result.input_tokens
            result.stop_reason =  ""
        except json.JSONDecodeError:
            logger.error("Response could not be json decoded: %s", response.model_dump_json())
            result.error_text = f"Response could not be json decoded {response.model_dump_json()}"
        except KeyError:
            logger.error("KeyError, unexpected response format: %s", response.model_dump_json())
            result.error_text = f"KeyError, unexpected response format: {response.model_dump_json()}"
    
        # For non-streaming requests we are keeping output_tokens_before_timeout and output_tokens same.
        result.output_tokens_before_timeout = result.output_tokens
        result.calculate_results()

        return result

