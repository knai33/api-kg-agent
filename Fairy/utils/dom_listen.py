import asyncio
import os
import re
import time
from datetime import datetime

import websockets
import json
from PIL import ImageGrab
from network import request_list, capture_network_requests
from ssim import is_significant_difference
from PIL import ImageGrab, ImageDraw
from db.db import conn


# 假设您有一个事件对象，用于存储事件的相关信息
class EventData:
    def __init__(self, filename, html_info, api_list):
        # self.event_type = event_type  # 事件类型（点击、失焦等）
        self.filename = filename
        self.html_info = html_info  # 提取的HTML信息部分
        self.api_list = api_list

    def to_dict(self):
        # 将对象的属性转换为字典
        return {
            "filename": self.filename,
            "html_info": self.html_info,
            "api_list": self.api_list
        }


# 截图函数，使用 Pillow 库截取屏幕并保存

last_screen_file = ""
count = 0
file_info = []
api_len = len(request_list)


async def take_screenshot(html_info, is_click=False):
    global last_screen_file
    global count
    global file_info
    global api_len
    await asyncio.sleep(1)
    # Ensure the directory exists
    script_dir = os.path.dirname(os.path.abspath(__file__))
    screenshot_dir = os.path.join(script_dir, "screenshot")

    if not os.path.exists(screenshot_dir):
        os.makedirs(screenshot_dir)
    # 截取整个屏幕
    screenshot = ImageGrab.grab()

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    count += 1

    filename = f"{screenshot_dir}\\{timestamp}-{count}.png"
    # 将截图保存到文件
    screenshot.save(filename)
    if not is_click and count > 1:

        if not is_significant_difference(last_screen_file, filename):
            print("Current screenshot is similar to the previous one, deleting it.")
            os.remove(filename)
            count -= 1
            return  # Exit the function if the current screenshot is deleted

    last_screen_file = filename
    cur_api_len = len(request_list)
    # print(request_list)
    new_api_list = []
    if cur_api_len > api_len:
        new_api_list = request_list[api_len:]
        api_len = cur_api_len

    event_data = EventData(filename, html_info, new_api_list).to_dict()
    file_info.append(event_data)
    with open('output.json', 'w', encoding='utf-8') as file:
        json.dump(file_info, file, ensure_ascii=False, indent=4)

    print(f"截图已保存为 {filename}")


async def listen_to_button_click(uri):
    # WebSocket URL，连接到正在运行的 Chrome 浏览器实例

    count = 0
    async with websockets.connect(uri) as websocket:
        # 启用 Runtime.evaluate 执行 JavaScript
        enable_runtime = {
            "id": 1,
            "method": "Runtime.enable"
        }

        await websocket.send(json.dumps(enable_runtime))

        # 使用 Runtime.evaluate 执行 JavaScript 代码，监听文档级别的 blur 事件
        add_event_listener = {
            "id": 2,
            "method": "Runtime.evaluate",
            "params": {
                "expression": """
                    document.addEventListener('click', function(e) {
                        //console.log('点击事件触发:', event.target);
                        
                        var html = e.target.outerHTML;
                        var x = e.screenX;
                        var y = e.screenY;
                        var log = '点击事件触发:'+html+ '，坐标: (' + x + ', ' + y + ')';
                        console.log(log)
                        
                    }, true);
                    
                    document.addEventListener('focusout', function(e) {
                        //console.log('失焦事件触发:', event.target);
                        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                            // 获取文本框的内容
                            var content = e.target.value;
                            var html = e.target.outerHTML
                            var log = '失焦事件触发:'+html+' 文本框内容:'+content
                            console.log(log);
                        } else {
                            var html = e.target.outerHTML
                            var log = '失焦事件触发:'+html
                            console.log(log)
                        }
                    }, true);            
                      
                     function registerIframeHandlers() {
                        const iframes = document.querySelectorAll('iframe');
                        
                        iframes.forEach(iframe => {
                            // 点击事件
                            if (!iframe.hasAttribute('data-click-listener')) {
                                try {
                                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                                    doc.addEventListener('click', (e) => {
                                        var html = e.target.outerHTML
                                        var x = e.screenX;
                                        var y = e.screenY;
                                        var log = '点击事件触发:'+html+ '，坐标: (' + x + ', ' + y + ')';
                                        //var log = '点击事件触发:'+html
                                        console.log(log)
                                        // console.log('iframe点击:', e.target);
                                        setTimeout(registerIframeHandlers, 1000);
                                    }, true);
                                    iframe.setAttribute('data-click-listener', 'true');
                                } catch (err) {
                                    console.error('点击监听器错误:', err);
                                }
                            }
                    
                            // 失焦事件
                            if (!iframe.hasAttribute('data-blur-listener')) {
                                try {
                                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                                    doc.addEventListener('focusout', (e) => {
                                        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                                            // 获取文本框的内容
                                            var content = e.target.value;
                                            var html = e.target.outerHTML
                                            var log = '失焦事件触发:'+html+' 文本框内容:'+content
                                            console.log(log);
                                        } else {
                                            var html = e.target.outerHTML
                                            var log = '失焦事件触发:'+html
                                            console.log(log)
                                        }
                                        //console.log('iframe失焦:', e.target);
                                        setTimeout(registerIframeHandlers, 1000);
                                    }, true);
                                    iframe.setAttribute('data-blur-listener', 'true');
                                } catch (err) {
                                    console.error('失焦监听器错误:', err);
                                }
                            }
                        });
                    }
                    
                    // 初始化
                    registerIframeHandlers();

                    // 监听DOM变化，处理动态加载的iframe（针对弹窗）
                    const observer = new MutationObserver(mutations => {
                        mutations.forEach(mutation => {
                            if (mutation.addedNodes.length) {
                                // 检查新增节点中是否有iframe
                                Array.from(mutation.addedNodes).forEach(node => {
                                    if (node.tagName === 'IFRAME') {
                                        setTimeout(() => registerIframeHandlers(), 500);
                                    }
                                    // 检查新增节点的子节点中是否有iframe
                                    if (node.querySelectorAll) {
                                        const iframes = node.querySelectorAll('iframe');
                                        if (iframes.length) {
                                            setTimeout(() => registerIframeHandlers(), 500);
                                        }
                                    }
                                });
                            }
                        });
                    });
                    
                    // 开始观察DOM变化
                    observer.observe(document.body, {
                        childList: true,
                        subtree: true
                    });
                
                """
            }
        }
        await websocket.send(json.dumps(add_event_listener))

        # 接收事件
        while True:
            response = await websocket.recv()
            message = json.loads(response)
            # 监听到 JavaScript 控制台输出时输出
            # 处理页面刷新事件
            if message.get('method') == 'Page.frameNavigated':
                print("页面刷新或导航事件触发")

            if message.get('method') == 'Runtime.consoleAPICalled':
                # if '点击' in message['params']['args'][0]['value']:
                #     print(message)
                #     value = message['params']['args'][0]['value']
                #     parts = value.split('坐标: ')
                #     prefix_part = parts[0]
                #     html_content = prefix_part.strip()
                #
                #     await take_screenshot(html_content, is_click=True)  # 截图并保存为点击事件文件
                if '点击' in message['params']['args'][0]['value']:
                    print(message)
                    value = message['params']['args'][0]['value']
                    parts = value.split('坐标: ')
                    prefix_part = parts[0]
                    html_content = prefix_part.strip()
                    await take_screenshot(html_content, is_click=True)  # 截图并保存为点击事件文件

                elif '失焦' in message['params']['args'][0]['value']:
                    value = message['params']['args'][0]['value']
                    html_content = value.strip()
                    await take_screenshot(html_content)  # 截图并保存为失焦事件文件
                    # print("失焦事件发生")
                    # print(message)



async def main():
    print("Starting...")
    # //todo 逗号 @ 转格式；
    # Run both capture_network_requests and listen_to_button_click concurrently
    uri = "ws://localhost:9222/devtools/page/909F98273E5BFBD9BA4A4910C269F138"
    await asyncio.gather(
        capture_network_requests(uri),
        listen_to_button_click(uri)
    )


# 启动事件循环
# asyncio.get_event_loop().run_until_complete(listen_to_button_click())

# async def main():
#     await take_screenshot("click_event.png")
#
# # 运行异步函数
# asyncio.run(main())

# Run the main function
if __name__ == "__main__":
    asyncio.run(main())
    # script_dir = os.path.dirname(os.path.abspath(__file__))
    # screenshot_dir = os.path.join(script_dir, "screenshot")
    # print(screenshot_dir)
"""
                    function registerIframeHandlers() {
                        const iframes = document.querySelectorAll('iframe');
                        
                        iframes.forEach(iframe => {
                            // 点击事件
                            if (!iframe.hasAttribute('data-click-listener')) {
                                try {
                                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                                    doc.addEventListener('click', (e) => {
                                        var html = e.target.outerHTML
                                        var x = e.screenX;
                                        var y = e.screenY;
                                        var log = '点击事件触发:'+html+ '，坐标: (' + x + ', ' + y + ')';
                                        //var log = '点击事件触发:'+html
                                        console.log(log)
                                        // console.log('iframe点击:', e.target);
                                        setTimeout(registerIframeHandlers, 1000);
                                    }, true);
                                    iframe.setAttribute('data-click-listener', 'true');
                                } catch (err) {
                                    console.error('点击监听器错误:', err);
                                }
                            }
                    
                            // 失焦事件
                            if (!iframe.hasAttribute('data-blur-listener')) {
                                try {
                                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                                    doc.addEventListener('focusout', (e) => {
                                        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                                            // 获取文本框的内容
                                            var content = e.target.value;
                                            var html = e.target.outerHTML
                                            var log = '失焦事件触发:'+html+' 文本框内容:'+content
                                            console.log(log);
                                        } else {
                                            var html = e.target.outerHTML
                                            var log = '失焦事件触发:'+html
                                            console.log(log)
                                        }
                                        //console.log('iframe失焦:', e.target);
                                        setTimeout(registerIframeHandlers, 1000);
                                    }, true);
                                    iframe.setAttribute('data-blur-listener', 'true');
                                } catch (err) {
                                    console.error('失焦监听器错误:', err);
                                }
                            }
                        });
                    }
                    
                    // 初始化
                    registerIframeHandlers();

                    // 监听DOM变化，处理动态加载的iframe（针对弹窗）
                    const observer = new MutationObserver(mutations => {
                        mutations.forEach(mutation => {
                            if (mutation.addedNodes.length) {
                                // 检查新增节点中是否有iframe
                                Array.from(mutation.addedNodes).forEach(node => {
                                    if (node.tagName === 'IFRAME') {
                                        setTimeout(() => registerIframeHandlers(), 500);
                                    }
                                    // 检查新增节点的子节点中是否有iframe
                                    if (node.querySelectorAll) {
                                        const iframes = node.querySelectorAll('iframe');
                                        if (iframes.length) {
                                            setTimeout(() => registerIframeHandlers(), 500);
                                        }
                                    }
                                });
                            }
                        });
                    });
                    
                    // 开始观察DOM变化
                    observer.observe(document.body, {
                        childList: true,
                        subtree: true
                    });

                    
"""
