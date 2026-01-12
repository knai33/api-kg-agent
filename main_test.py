import asyncio
import os

from loguru import logger

from Fairy.fairy import FairyCore

os.environ["OPENAI_API_KEY"] = "sk-zk2d9aae813fa366fafd3e4d9548327d66e68536902222b2"
os.environ["OPENAI_BASE_URL"] = "https://api.zhizengzeng.com/v1"

ADB_PATH = "C:/Users/neosunjz/AppData/Local/Android/Sdk/platform-tools/adb.exe -e"

async def main():
    fairy = FairyCore()
    instruction = "Delete all pictures in an album and empty the recycle bin."
    await fairy.start(instruction)

if __name__ == '__main__':
    asyncio.run(main())
