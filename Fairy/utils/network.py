import asyncio
import re

import websockets
import json

request_id_to_integer_id = {}
request_id_to_url = {}
request_list = []

async def capture_network_requests(uri):
    async with websockets.connect(uri) as websocket:
        # 启用网络域
        enable_network = {
            "id": 1,
            "method": "Network.enable"
        }
        await websocket.send(json.dumps(enable_network))

        # 监听网络事件
        while True:
            # print(request_id_to_url)
            response = await websocket.recv()
            message = json.loads(response)
            # print(message)
            if message.get("id") and message.get("result"):
                print(message)
                request_id = request_id_to_integer_id.get(message.get("id"))
                request_id_to_url[request_id]["response_body"] = message.get("result").get("body")
                request_list.append(request_id_to_url[request_id])
                # print(request_id_to_url)

            # 监听网络请求
            if "method" in message and message["method"] == "Network.requestWillBeSent" and message["params"]["type"] in ['Fetch', 'XHR']:
                print(message)
                request = message["params"]["request"]
                headers = message["params"]["request"]["headers"]
                request_id = message["params"].get("requestId", "")

                url_struct = {
                    "request_id": request_id,
                    "url": request.get("url"),
                    "method": request.get("method"),
                    "request_content_type": headers.get("Content-Type") or headers.get("content-type") or "",
                    "post_data": request.get("postData")
                }
                request_id_to_url[request_id] = url_struct
            #

            if "method" in message and message["method"] == "Network.responseReceived" and message["params"]["type"] in ['Fetch', 'XHR']:
                print(message)
                response = message["params"]["response"]
                request_id = message["params"].get("requestId", "")
                # 获取响应头
                headers = message["params"]["response"]["headers"]

                # 查找 Content-Type（不区分大小写）
                content_type = headers.get("Content-Type") or headers.get("content-type") or ""

                # 记录 Content-Type（如果不存在则记录空字符串）
                request_id_to_url[request_id]["response_content_type"] = content_type

                if response.get("mimeType", "").startswith("application/json") or response.get("mimeType", "").startswith("text/plain") or response.get("mimeType", "").startswith("application/vnd.api+json"): ## 修复bug-delete返回空值 不捕获，即默认api必须要返回值。。 针对flarum： application/vnd.api+json
                    integer_id = int(str(request_id).replace(".", ""))  # 将小数点去掉并转为整数
                    request_id_to_integer_id[integer_id] = request_id  # 保存映射关系

                    # 发送请求获取响应体的内容
                    get_response_body = {
                        "id": integer_id,
                        "method": "Network.getResponseBody",
                        "params": {
                            "requestId": request_id
                        }
                    }
                    await websocket.send(json.dumps(get_response_body))


# asyncio.get_event_loop().run_until_complete(capture_network_requests())
