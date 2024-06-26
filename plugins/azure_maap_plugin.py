import json
import logging
import time

import requests
import urllib3

from plugins import plugin
from result import RequestResult

urllib3.disable_warnings()
"""
Example plugin config.yaml:

plugin: "azure_maap_plugin"
plugin_options:
    url: "https://meta-llama-3-8b.eastus2.inference.ml.azure.com/score"
    key: "55yMR1O9h8322d0p5SrGXG2rfhrZGSXg"
    deployment: "meta-llama-3-8b-2"
"""

required_args = ["url", "key", "deployment"]

logger = logging.getLogger("user")

# This plugin is written primarily for testing vLLM, though it can be made
# to work for other runtimes which conform to the OpenAI API, as required.
class AzureMaapPlugin(plugin.Plugin):
    def __init__(self, args):
        self._parse_args(args)

    def _parse_args(self, args):
        for arg in required_args:
            if arg not in args:
                logger.error("Missing plugin arg: %s", arg)

       
        self.request_func = self.request_http

        self.host = args.get("url")
        self.key = args.get("key")

        self.model_name = args.get("deployment")
        

    def request_http(self, query: dict, user_id: int, test_end_time: float = 0):

        result = RequestResult(user_id, query.get("text"), query.get("input_tokens"))

        result.start_time = time.time()

        headers = {'Content-Type':'application/json', 'Authorization':('Bearer '+ self.key), 'azureml-model-deployment': self.model_name }

        
        data = {
            "input_data": {
                "input_string": [
                    {
                        "role": "user",
                        "content": query.get("text"),
                    },
                ],
                "parameters": {
                    "temperature": 0.1,
                    "top_p": 0.6,
                    "max_new_tokens": query["output_tokens"],
                },
            }
        }
       
        if self.model_name is not None:
            data["model"] = self.model_name

        response = None
        try:
            response = requests.post(self.host, headers=headers, json=data, verify=False)
            response.raise_for_status()
        except requests.exceptions.ConnectionError as err:
            result.end_time = time.time()
            result.error_text = repr(err)
            if response is not None:
                result.error_code = response.status_code
            logger.exception("Connection error")
            return result
        except requests.exceptions.HTTPError as err:
            result.end_time = time.time()
            result.error_text = repr(err)
            if response is not None:
                result.error_code = response.status_code
            logger.exception("HTTP error")
            return result

        result.end_time = time.time()

        logger.debug("Response: %s", json.dumps(response.text))

        try:
            message = json.loads(response.text)
            if "output" in message:
                message= message["output"]
            
            result.output_text = str(message)
            result.output_tokens = self.num_tokens_from_string(result.output_text)
            result.input_tokens = self.num_tokens_from_string(query.get("text"))
            result.stop_reason =  ""
        except json.JSONDecodeError:
            logger.exception("Response could not be json decoded: %s", response.text)
            result.error_text = f"Response could not be json decoded {response.text}"
        except KeyError:
            logger.exception("KeyError, unexpected response format: %s", response.text)
            result.error_text = f"KeyError, unexpected response format: {response.text}"

        # For non-streaming requests we are keeping output_tokens_before_timeout and output_tokens same.
        result.output_tokens_before_timeout = result.output_tokens
        result.calculate_results()

        return result

