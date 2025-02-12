# -*- coding: utf-8 -*-
"""
功能：从品牌文件夹中的 jsonl 文件中下载图片
实现：遍历所有文件夹查询 .jsonl 文件，读取文件中的图片 url，从 url 下载图片到指定品牌文件夹副本
"""
import json
import os
import queue
import threading
import time
from os import path
import asyncio
import requests
from tqdm import tqdm

# 创建连接池
headers = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'zh-CN,zh-Hans;q=0.9',
    'Connection': 'keep-alive',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
}

total, download = 0, 0
q = queue.Queue()  # 创建队列对象
lock = threading.Lock()  # 创建一个共享的锁


# 整理任务，并添加到队列中
def task_maker(src, dst=None, num_per_item: int = None):
    global q, total
    if dst is None:
        dst = src + "-Images"
    src = src+'-Meta'
    for root, dirs, files in os.walk(src):
        for file in files:
            if file.endswith("items.jsonl"):
                file = path.join(root, file)
                # 路径的 src 替换为 dst 得到目标路径
                f_ = file.replace(src, dst)
                dst_ = path.dirname(f_)
                # 读取 jsonl 文件中的每一行数据
                with open(file, "r", encoding="utf-8") as f:
                    items = f.readlines()
                    # 遍历 Item
                    for item in items:
                        urls = []
                        item_id = None
                        # 将每一行数据转换为字典
                        item = json.loads(item)
                        # 遍历字典中的每一项
                        for k, v in item.items():
                            # 如果 Key 中包含 "id"，则说明是item id
                            if "id" in k:
                                item_id = v
                            # 如果 Key 中包含 "image"，则说明是图片 url
                            if "image" in k:
                                # 判断是 str 还是 list
                                if isinstance(v, str):
                                    urls.append(v)
                                elif isinstance(v, list):
                                    urls.extend(v)
                        # 每个 item 只下载 num_per_item 张图片
                        if num_per_item is not None:
                            urls = urls[:num_per_item]
                        # 遍历图片 url, 命名为 item_id-index.postfix
                        for i, url in enumerate(urls):
                            # 获取图片后缀名
                            postfix = url[url.rfind("."):]
                            name = f"{item_id}-{i}{postfix}"
                            dst_folder = path.join(dst_, item_id)
                            dst_file = path.join(dst_folder, name)
                            # 判断是否已经下载过
                            if path.isfile(dst_file):
                                continue
                            # 加入任务
                            q.put({"url": url, "dst": path.join(dst_, item_id), "name": f"{item_id}-{i}{postfix}"})
                            total += 1


def downloader():
    global q, download
    while True:
        # 获取数据
        data = q.get()
        if data is None:
            continue
        # 下载图片
        download_url(data["url"], data["dst"], data["name"])
        download += 1


def download_url(url, dst, name=None):
    if not path.isdir(dst):
        os.makedirs(dst, exist_ok=True)
    # 如果没提供 name, 从 url 中获取图片名
    if name is None:
        name = url[url.rfind("/") + 1:]
    # 判断是否已经下载过
    if path.isfile(path.join(dst, name)):
        return
    # 下载图片
    with open(path.join(dst, name), 'wb') as f:
        img = requests.get(url, headers=headers).content
        f.write(img)


def log():
    global total, download
    last = download
    with tqdm(total=total, ncols=100) as pbar:
        while True:
            pbar.update(download - last)
            pbar.total = total
            last = download
            time.sleep(1)


async def main(folders=None, num_workers=16, images_per_item=None):
    if folders is None:
        folders = ["Meta/YOOX"]
    for folder in folders:
        threading.Thread(target=task_maker, args=(folder, None, images_per_item)).start()

    threading.Thread(target=log).start()
    threads = [threading.Thread(target=downloader) for _ in range(num_workers)]
    for t in threads:
        t.start()


def async_main(**kwargs):
    asyncio.run(main(kwargs))


if __name__ == '__main__':
    asyncio.run(main(
        folders=["D:\Spider\Meta\YOOX"],
        num_workers=16, images_per_item=None))
    pass
