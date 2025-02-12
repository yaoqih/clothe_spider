import os
from pprint import pprint

# os.environ['HTTP2_SESSION_RECV_WINDOW'] = '0'
# os.environ['HTTP2_STREAM_RECV_WINDOW'] = '0'
import json
import os.path
import time
from abc import abstractmethod

import jsonlines
import asyncio

from jsmin import jsmin
from playwright.async_api import async_playwright
# import sys
# import playwright
# playwright.log.enable(sys.stdout)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 Edg/116.0.1938.81"

class Spider:
    def __init__(self, test_mode=False):
        self.root = None
        self.category_urls = None
        self.test_mode = test_mode
        self.failed_tasks = []
        # 用于记录爬取信息
        #  - category: 性别-品类-子品类
        #  - start_time: 开始时间
        #  - num_done: 已爬取的商品数量
        #  - num_new: 新爬取的商品数量
        self.log_info = dict()

    @staticmethod
    async def read_json(json_file):
        assert os.path.isfile(json_file), f"{json_file} not exist"
        with open(json_file, "r") as f:
            min_f = jsmin(f.read())
            return json.loads(min_f)

    @staticmethod
    async def read_done_item_ids(dst_jsonl):
        """
        读取已经爬取过的商品 id
        """
        if not os.path.exists(dst_jsonl):
            return set()
        ids = set()
        with jsonlines.open(dst_jsonl) as reader:
            for item in reader:
                ids.add(item['id'])
        return ids

    @staticmethod
    async def scroll_to_bottom(page, gap=1200, sleep_time=0.15):
        if gap == 0:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            return
        max_height, height = await page.evaluate("function(){return document.body.scrollHeight}"), 0
        while max_height >= height:
            height += gap
            await page.evaluate(f"window.scrollTo(0, {height});")
            await asyncio.sleep(sleep_time)

    @staticmethod
    async def write_item_info(item_info, dst_jsonl):
        """
        将商品信息以 a 模式写入文件dst_jsonl
        """
        # Jsonl 写入
        with jsonlines.open(dst_jsonl, mode='a') as writer:
            writer.write(item_info)

    @abstractmethod
    async def next_page_btn(self, page):
        """
        获取下一页按钮
        """
        ...

    @abstractmethod
    async def id_from_url(self, url):
        """
        从 item_url 中获取商品 id
        """
        ...

    @abstractmethod
    async def items_in_page(self, page):
        """
        获取当前页面的所有商品的 url
        """
        ...

    @abstractmethod
    async def info_of_item(self, page):
        """
        获取当前商品详情页面的商品信息，包括图像 urls、文本描述
        """
        ...

    @staticmethod
    async def convert_category_url(url):
        """
        将类别 url 转换为爬虫可用的 url, 一般不需要重写, 用于网页有多个顶级域名的情况；
        如 Farfetch 的 cn 域名通常被限流，可在此处改为 com 域名
        """
        return url

    async def log(self):
        """
        输出日志
        """
        log_width = 88
        while True:
            if len(self.log_info) == 0:
                await asyncio.sleep(2)
                continue
            print(f"{'=' * (log_width // 2)} Log {'=' * (log_width // 2)}")
            keys = sorted(self.log_info.keys())  # 对日志按照 key 进行排序
            for key in keys:
                log_str = f"{key[:40]}:".ljust(40)
                log_str += f"{self.log_info[key]['num_new']} new, ".rjust(13)
                log_str += f"{self.log_info[key]['num_done'] + self.log_info[key]['num_new']} total".rjust(12)
                if end_info := self.log_info[key].get('end'):
                    log_str += end_info
                elif self.log_info[key]['num_new'] > 0:
                    log_str += f", {(time.time() - self.log_info[key]['start_time']) / self.log_info[key]['num_new']:.2f} s/item"
                print(log_str)
            earliest_time = min([self.log_info[key]['start_time'] for key in self.log_info])
            total_new = sum([self.log_info[key]['num_new'] for key in self.log_info])
            total_done = sum([self.log_info[key]['num_done'] for key in self.log_info])

            speed = min((time.time() - earliest_time) / (total_new + 0.0001), 999.99)
            print(
                f"{total_new} new, {total_done + total_new} total, {speed:.2f} s/item")
            print(f"{'=' * (log_width+5)}")
            await asyncio.sleep(5)

    async def _print(self, message):
        if self.test_mode:
            print(message)

    async def category_spider(self, gender: str, category: str, sub_category: str = None, headless=False,
                              semaphore=asyncio.Semaphore(5),
                              next_page_click=True):
        """
        用来爬去一个品类的服装页面，该页面应该包含商品列表、页码/总页数、换页按钮等元素
        :param semaphore: 限制最大并行数
        :param gender: 性别（或类型，如有 kids 等）
        :param category: 服装类别
        :param sub_category:  服装类别的子分类
        :param headless: 是否启用无头浏览器
        """
        async with semaphore:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=headless, args=['--start-maximized'])
                context = await browser.new_context(
                    extra_http_headers={"Accept-Language": "en-US,en;q=0.9",
                                        'Accept-Encoding': 'gzip, deflate, br',
                                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                                        'Connection': 'keep-alive',
                                        'Sec-Fetch-Dest': 'document',
                                        'Sec-Fetch-Mode': 'navigate',
                                        'Sec-Fetch-Site': 'same-origin',
                                        },
                    user_agent=USER_AGENT,
                    locale="en-GB",  # zh-CN、en-GB
                    no_viewport=True,
                )
                # 拦截 webp
                # abort_types = ['media', 'font'] #, "image"] #'stylesheet']
                # await context.route("**/*", lambda
                #     route: route.abort() if route.request.resource_type in abort_types else route.continue_())
                page = await context.new_page()
                # await page.route( "**", lambda route: route.continue_(http_version="http/1.1"))
                # await page.route("**/*.{png,jpg,jpeg}", lambda route: route.abort())  # 禁止加载图片

                # 获取服装类别的 url, 读取类别对应的 item.jsonl 文件
                category_url = self.category_urls[gender][category]
                category_folder = os.path.join(self.root, gender, category)
                if sub_category:
                    category_url = category_url[sub_category]
                    category_folder = os.path.join(category_folder, sub_category)
                category_url = await self.convert_category_url(category_url)
                if not os.path.exists(category_folder):
                    os.makedirs(category_folder)
                dst_jsonl = os.path.join(category_folder, "items.jsonl")
                done_item_ids = await self.read_done_item_ids(dst_jsonl)

                # 记录到日志中
                log_key = f"{gender}/{category}"
                if sub_category:
                    log_key += f"/{sub_category}"
                self.log_info[log_key] = {'start_time': time.time(), 'num_done': len(done_item_ids), 'num_new': 0}

                # 开始爬取
                page_ = 0
                category_max_try, category_try_ = 8, 0
                # 类别页面的 Loop
                while True:
                    try:
                        if page_ == 0:
                            await page.goto(category_url, wait_until="domcontentloaded")
                        await self.scroll_to_bottom(page)  # 滚动到页面底部，以防有网页动态加载
                        await asyncio.sleep(1)  # 给页面加载留出时间
                        item_urls = await self.items_in_page(page)  # 获取当前页面的所有商品的 url
                        await self._print(f"PAGE: {page_}, ITEMS: {len(item_urls)}")
                    except Exception as e:
                        print(e)
                        category_try_ += 1
                        if category_try_ >= category_max_try:
                            print(f"当前品类 {log_key} 页面爬取失败：{e}")
                            self.log_info[log_key]['end'] = f', Fail to Open Page: {e} {page.url}'
                            self.failed_tasks.append([gender, category, sub_category])
                            break
                        continue

                    # 如果当前页面没有商品，则说明已经到达最后一页
                    if len(item_urls) == 0:
                        self.log_info[log_key]['end'] = ', finished'
                        break

                    # 根据 id 去除已经爬取过的商品
                    item_urls = [url for url in item_urls if await self.id_from_url(url) not in done_item_ids]

                    page_ += 1  # 当前页面的页码
                    item_index = 0  # 当前页面正在爬取的商品的索引
                    item_max_try, item_try_ = 5, 0
                    item_page = await context.new_page()
                    while item_index < len(item_urls):
                        item_url = item_urls[item_index]
                        item_id = await self.id_from_url(item_url)
                        item_info = {'id': item_id}
                        # 获取商品信息
                        try:
                            await item_page.goto(item_url, wait_until="domcontentloaded")
                            await self.scroll_to_bottom(item_page)  # 滚动到页面底部，以防有网页动态加载
                            item_dict = await self.info_of_item(item_page)
                            item_info.update(item_dict)  # 获取商品信息
                        except Exception as e:
                            print(e)
                            item_try_ += 1
                            if item_try_ >= item_max_try:
                                print(f"Failed to open {item_url} after {item_max_try} tries")
                                item_index += 1
                            await asyncio.sleep(10)  # 缓冲时间，防止被 ban
                            continue

                        item_info['gender'] = gender
                        item_info['category'] = category
                        if sub_category:
                            item_info['sub_category'] = sub_category
                        await self.write_item_info(item_info, dst_jsonl)
                        # 更新日志和计数器
                        item_index += 1
                        done_item_ids.add(item_id)
                        self.log_info[log_key]['num_new'] += 1
                    await item_page.close()

                    # 如果存在下一页按钮，则点击下一页按钮
                    try:
                        next_page_btn = await self.next_page_btn(page)
                        if next_page_btn:
                            old_url = page.url
                            if next_page_click:
                                await next_page_btn.click()
                            else:
                                await page.goto(next_page_btn, wait_until="domcontentloaded")
                            # 等待 url 发生变化
                            wait_time = 0
                            while page.url == old_url and wait_time < 10:
                                await asyncio.sleep(1.0)
                                wait_time += 1
                            await asyncio.sleep(1.0)  # 给页面加载留出时间
                        else:  # 未找到下一页按钮，说明已经到达最后一页
                            self.log_info[log_key]['end'] = ', finished'
                            break
                    except Exception as e:
                        print(e)
                        self.log_info[log_key]['end'] = f', Fail to Next Page: {e} {page.url}'
                        self.failed_tasks.append([gender, category, sub_category])
                        break

    async def async_run(self, root: str, category_json: str, concurrency: int = 2, headless=False, next_page_click=True):
        self.root = root
        with open(category_json, 'r') as f:
            self.category_urls = json.load(f)
        semaphore = asyncio.Semaphore(concurrency)
        task_list = [asyncio.create_task(self.log())]

        for gender in self.category_urls:
            for category in self.category_urls[gender]:
                if isinstance(self.category_urls[gender][category], str):
                    task = asyncio.create_task(self.category_spider(gender, category,
                                                                    semaphore=semaphore, headless=headless,
                                                                    next_page_click=next_page_click))
                    task_list.append(task)
                else:
                    for sub_category in self.category_urls[gender][category]:
                        task = asyncio.create_task(self.category_spider(gender, category, sub_category,
                                                                        semaphore=semaphore, headless=headless,
                                                                        next_page_click=next_page_click))
                        task_list.append(task)

        await asyncio.gather(*task_list)

        task_list = [asyncio.create_task(self.log())]
        for gender, category, sub_category in self.failed_tasks:
            task = asyncio.create_task(self.category_spider(gender, category,
                                                            semaphore=semaphore, headless=headless,
                                                            next_page_click=next_page_click))
            task_list.append(task)
        await asyncio.gather(*task_list)


class ItalistSpider(Spider):
    def __init__(self, test_mode=False):
        super().__init__(test_mode=test_mode)

    # TODO: 以下仅适用于 Italist
    async def next_page_btn(self, page):
        """
        获取下一页按钮
        """
        old_url = page.url
        # https://www.italist.com/cn/women/clothing/coats-jackets/blazers/29/?skip=180
        # 如果有 skip= 则把 skip= 后面的数字加 60
        if old_url.find('skip=') != -1:
            new_url = old_url[:old_url.find('skip=') + 5] + str(int(old_url[old_url.find('skip=') + 5:]) + 60)
        else:
            new_url = old_url + '?skip=60'


        return new_url

    # TODO: 以下仅适用于 Italist
    async def id_from_url(self, url):
        # https://www.italist.com/cn/women/clothing/underwear-nightwear/bodysuits/body/13238321/13406013/saint-laurent/
        # id : 13238321/13406013
        url = url[:url.rfind('/')]
        _ = url.split('/')
        return '/'.join(_[-3:-1])


    # TODO: 以下仅适用于 Italist
    async def items_in_page(self, page):
        """
        获取当前页面的所有商品的 url
        """
        # div id="product-page-container"
        items_div = await page.query_selector("div[id='product-page-container']")
        assert items_div, "未找到当前类别的 product-page-container, 也许页面结构已经改变！"
        # 获取 items_div 所有 a 标签的 href 属性
        items = await items_div.query_selector_all("a")
        items = await asyncio.gather(*[item.get_attribute("href") for item in items])
        items = [item for item in items if item]  # 去除 None item
        # 添加 https://www.italist.com 前缀
        items = ["https://www.italist.com" + item if not item.startswith('http') else item for item in items]
        ids = await asyncio.gather(*[self.id_from_url(item) for item in items])
        # 检验 id 长度和格式 : 13238321/13406013
        items = [item for item, id_ in zip(items, ids) if len(id_) == 17 and id_.find('/') == 8]
        return items

    # TODO: 以下仅适用于 Italist
    async def info_of_item(self, page):
        """
        获取当前商品详情页面的商品信息，包括图像 urls、文本描述
        """
        item_info = dict()
        # 基础信息 div class 包含 product-actions-sticky
        basic_info = await page.query_selector("div[class*='product-actions-sticky']")
        assert basic_info, "未找到商品详情页的div class product-actions-sticky, 也许页面结构已经改变！"
        # 品牌名 h2 class="jsx-2052347248 brand"
        brand = await basic_info.query_selector("h2[class*='jsx-2052347248 brand']")
        # 品类 <h1 class="jsx-2052347248 model">Crewneck Long-sleeved Jumpsuit</h1>
        item_category = await basic_info.query_selector("h1[class*='jsx-2052347248 model']")
        # 如果存在则添加到 item_info 中
        # if color:
        #     item_info["color"] = await color.inner_text()
        if brand:
            item_info["brand"] = await brand.inner_text()
        if item_category:
            item_info["item"] = await item_category.inner_text()

        # 获取 div class="jsx-3874064703 accordion-heading" 或 div class="jsx-862246428 accordion-content"
        accordion_divs = await basic_info.query_selector_all("div[class*='jsx-3874064703 accordion-heading'], div[class*='jsx-862246428 accordion-content']")
        for accordion_div in accordion_divs:
            if "accordion-heading" in await accordion_div.get_attribute("class"):
                key_ = await accordion_div.inner_text()
                item_info[key_] = []
            elif key_:
                text = await accordion_div.inner_text()
                if text not in item_info[key_]:
                    item_info[key_].append(text)

        # 获取 carousel_div 所有 img 标签的 src 属性
        # div class ="jsx-2140263580 carousel-item"
        # div class="jsx-1976571714 image-product-info-container"
        img_div = await page.query_selector("div[class*='jsx-1976571714 image-product-info-container']")
        imgs = await img_div.query_selector_all("img")
        urls = await asyncio.gather(*[img.get_attribute("src") for img in imgs])
        # 筛选出 jpg 图片
        urls = [url for url in urls if url and url.endswith('.jpg')]
        item_info["image_urls"] = urls

        return item_info


class FARFETCHSpider(Spider):
    def __init__(self):
        super().__init__()

    @staticmethod
    async def convert_farfetch_json(json_file):
        # https://www.farfetch.cn/ca/shopping/men/clothing-2/items.aspx?page=1&view=96&sort=3&category=136420
        category_dict = await Spider.read_json(json_file)
        new_category_dict = category_dict.copy()
        # 原始 dict 中存储的是 link 中的 category code （如 136420），需要转换为 url
        # 如果是男性则中间是 men/clothing-2， 女性则是 women/clothing-1
        middle_part = {'men': 'men/clothing-2', 'women': 'women/clothing-1'}
        for gender in category_dict:
            for category in category_dict[gender]:
                for sub_category in category_dict[gender][category]:
                    code = category_dict[gender][category][sub_category]
                    url = f"https://www.farfetch.cn/ca/shopping/{middle_part[gender]}/items.aspx?page=1&view=96&sort=3&category={code}"
                    new_category_dict[gender][category][sub_category] = url
        dst_json = json_file[:json_file.rfind('.')] + '-convert.json'
        with open(dst_json, 'w') as f:
            json.dump(new_category_dict, f)

    @staticmethod
    async def convert_category_url(url):
        """
        将类别 url 转换为爬虫可用的 url, 一般不需要重写, 用于网页有多个顶级域名的情况；
        如 Farfetch 的 cn 域名通常被限流，可在此处改为 com 域名
        """
        return url.replace('www.farfetch.cn', 'www.farfetch.com')

    # TODO: 以下仅适用于 FARFETCH
    async def next_page_btn(self, page):
        """
        获取下一页按钮
        """
        # a data-testid="page-next" and aria-hidden="false"
        next_page_btn = await page.query_selector("a[data-testid='page-next'][aria-hidden='false']")
        return next_page_btn

    # TODO: 以下仅适用于 FARFETCH
    async def id_from_url(self, url):
        return url[url.rfind('item-') + 5:url.rfind('.aspx')]

    # TODO: 以下仅适用于 FARFETCH
    async def items_in_page(self, page):
        """
        获取当前页面的所有商品的 url
        """
        # 获取所有 li 标签包含 data-testid="productCard"
        # section id="portal-slices-listing"
        block = await page.query_selector("section[id='portal-slices-listing']")
        assert block, ("未找到类别页面的 section[id='portal-slices-listing'], 可能以下原因：\n"
                       "1. 网站结构变动，需重新编写爬虫 items_in_page 代码；\n"
                       "2. 404 页面，访问过多导致被限流；")
        items = await block.query_selector_all("li[data-testid='productCard']")
        # 获取 所有 item 中 a 标签（data-component="ProductCardLink"）的 href 属性
        items = await asyncio.gather(*[item.query_selector("a[data-component='ProductCardLink']") for item in items])
        items = await asyncio.gather(*[item.get_attribute("href") for item in items])
        items = [item for item in items if item]  # 去除 None item
        items = ["https://www.farfetch.cn" + item if not item.startswith('http') else item for item in
                 items]  # 前面加上 https://www.farfetch.cn
        return items

    # TODO: 以下仅适用于 FARFETCH
    async def info_of_item(self, page):
        """
        获取当前商品详情页面的商品信息，包括图像 urls、文本描述
        """
        item_info = dict()

        # 等到页面中 div data-component="TabPanels"加载完成
        await page.wait_for_selector("div[id='tabpanel-0'], div[data-component='AccordionPanel']")
        # 商品细节 div class="ltr-9vdnw4"
        item_details = await page.query_selector("div[id='tabpanel-0'], div[data-component='AccordionPanel']")
        assert item_details, "未找到商品详情页的 TabPanels, 也许页面结构已经改变！"
        # 系列 <p class="ltr-xkwp1l-Body e1m5ny110">
        series = await item_details.query_selector("p[class*='ltr-xkwp1l-Body']")
        if series:
            item_info["series"] = await series.inner_text()
        # Key   h4 class="ltr-2pfgen-Body-BodyBold"  Values  p class="ltr-4y8w0i-Body"
        head_texts = await item_details.query_selector_all(
            "a[class*='ltr-8gbn9h-Heading-HeadingBold'], p[data-component*='Body'], li[data-component*='Body'], h4[data-component*='BodyBold']")
        start_index = 0
        # 找到第一个 a[class*='ltr-8gbn9h-Heading-HeadingBold'] 的 inner_text 作为 品牌
        for i in range(len(head_texts)):
            if "ltr-8gbn9h-Heading-HeadingBold" in await head_texts[i].get_attribute("class"):
                item_info["brand"] = await head_texts[i].inner_text()
                start_index = i + 1
                break
        # 下一个是品类
        item_info["item"] = await head_texts[start_index].inner_text()
        # 如果第二个是p data-component="Body" 则是描述
        if await head_texts[1].get_attribute("data-component") == "Body":
            item_info["description"] = await head_texts[start_index + 1].inner_text()
            start_index += 2
        else:
            start_index += 1
        # 其余的如果是 h4 则作为 key, 如果是 p 则作为 value
        key_ = None
        information = dict()
        for i in range(start_index, len(head_texts)):
            if "ltr-2pfgen-Body-BodyBold" in await head_texts[i].get_attribute("class"):
                key_ = await head_texts[i].inner_text()
                information[key_] = []
            elif key_:
                text = await head_texts[i].inner_text()
                if text not in information[key_]:
                    information[key_].append(text)
        item_info["information"] = information

        # 查找页面中所有图片，class="ltr-1w2up3s" 的 img, 该 img 的 src 属性即为图片的 url, 但是有重复的
        imgs = await page.query_selector_all("img[class*='ltr-1w2up3s']")
        assert imgs, "未找到商品详情页的 img[class*='ltr-1w2up3s'], 也许页面结构已经改变！"
        urls = await asyncio.gather(*[img.get_attribute("src") for img in imgs])
        urls = list(dict.fromkeys(urls))  # 去重，但不改变顺序
        item_info["image_urls"] = urls

        return item_info


class YOOXSpider(Spider):
    def __init__(self):
        super().__init__()

    # TODO: 以下仅适用于 YOOX
    async def next_page_btn(self, page):
        """
        获取下一页按钮
        """
        # Span class="triangle-arrow triangle-arrow-right"
        next_page_btn = await page.query_selector("span[class*='triangle-arrow-right']")
        return next_page_btn

    # TODO: 以下仅适用于 YOOX
    async def id_from_url(self, url):
        return url.split('/item#')[0].split('/')[-1]

    # TODO: 以下仅适用于 YOOX
    async def items_in_page(self, page):
        """
        获取当前页面的所有商品的 url
        """
        # 获取所有 class 标签包含 itemContainer 的 div
        items = await page.query_selector_all("div[class*='itemContainer']")
        # 获取 所有 item 第一个 a 标签的 href 属性
        items = await asyncio.gather(*[item.query_selector("a") for item in items])
        items = await asyncio.gather(*[item.get_attribute("href") for item in items])
        items = [item for item in items if item]  # 去除 None item
        items = ["https://www.yoox.com" + item if not item.startswith('http') else item for item in
                 items]  # 前面加上 https://www.yoox.com
        return items

    # TODO: 以下仅适用于 YOOX
    async def info_of_item(self, page):
        """
        获取当前商品详情页面的商品信息，包括图像 urls、文本描述
        """
        # TODO: 以下仅适用于 YOOX
        item_info = dict()
        # 基础信息 class="ItemInfo_item-info__KcZIo" 的 div
        basic_info = await page.query_selector("div[class*='ItemInfo_item-info__KcZIo']")
        assert basic_info, "未找到商品详情页的 ItemInfo_item-info__KcZIo, 也许页面结构已经改变！"
        # 颜色 div class="MuiBody2-body2 ColorPicker_color-selected-title__oB1iK"
        color = await page.query_selector("div[class*='ColorPicker_color-selected-title__oB1iK']")
        brand = await basic_info.query_selector("h1[class*='MuiTitle3-title3']")  # 品牌名，class 为 MuiTitle3-title3的 h1
        series = await basic_info.query_selector("b")  # 系列，品牌同级的下一个h2 class="MuiBody1-body1"
        item_category = await basic_info.query_selector(
            "h2[class='MuiBody1-body1 ItemInfo_microcat__ffpIA']")  # 品类 class="MuiBody1-body1 ItemInfo_microcat__ffpIA"
        # 如果存在则添加到 item_info 中
        if color:
            item_info["color"] = await color.inner_text()
        if brand:
            item_info["brand"] = await brand.inner_text()
        if series:
            item_info["series"] = await series.inner_text()
        if item_category:
            item_info["item"] = await item_category.inner_text()

        # 获取页面中 class="item_details-container__u52Wd" 的第一个 div
        item_details = await page.query_selector("div[class*='item_details-container__u52Wd']")
        assert item_details, "未找到商品详情页的 item_details-container__u52Wd, 也许页面结构已经改变！"

        # 获取item_details中所有 class 为 MuiTitle4-title4 或 MuiBody1-body1 的 span
        information = dict()
        spans = await item_details.query_selector_all("span[class*='MuiTitle4-title4'], span[class*='MuiBody1-body1']")
        key_ = None
        for span in spans:
            # 如果 span 的 class 是 MuiTitle4-title4 则作为 key
            if "MuiTitle4-title4" in await span.get_attribute("class"):
                key_ = await span.inner_text()
                information[key_] = []
            elif key_:
                text = await span.inner_text()
                if text not in information[key_]:
                    information[key_].append(text)
        item_info["information"] = information

        # 查找页面中所有 style 中包含 zoom-in 的 span, 该 span 中的 img 标签的 src 属性即为图片的 url
        spans = await page.query_selector_all("span[style*='zoom-in']")
        urls = await asyncio.gather(*[span.query_selector("img") for span in spans])
        urls = await asyncio.gather(*[url.get_attribute("src") for url in urls])
        urls = [url[:url.find(".jpg") + 4] for url in urls]  # 截取到.jpg
        item_info["image_urls"] = urls

        return item_info


class ADIDASSpider(Spider):
    def __init__(self):
        super().__init__()

    # 以下仅适用于 ADIDAS
    async def next_page_btn(self, page):
        """
        获取下一页按钮
        """
        # div class="arrow-content"
        btn_div = await page.query_selector("div[class*='arrow-content']")
        # 获取所有子节点 div
        btns = await btn_div.query_selector_all("div")
        # 获取最后一个 div
        next_page_btn = btns[-1]
        # 判断 class 是否是 disable
        class_ = await next_page_btn.get_attribute("class")
        if "disable" in class_:
            return None
        else:
            # span class="iconfont iconsilde-right"
            next_page_btn = await next_page_btn.query_selector("span[class*='iconfont iconsilde-right']")
            return next_page_btn

    # 以下仅适用于 ADIDAS
    async def id_from_url(self, url):
        #https://www.adidas.com.hk/item/IT7440?rt=pdp&locale=en_GB
        return url[url.rfind('/')+1:url.find('?')]

    # 以下仅适用于 ADIDAS
    async def items_in_page(self, page):
        """
        获取当前页面的所有商品的 url
        """
        # page 滚动到底部，间隔 1s
        for _ in range(15):
            await page.mouse.wheel(0, 2000)  # 连续向下滚动，每次100像素
            await asyncio.sleep(1)
        # 获取所有 a class="card-swiper"
        items = await page.query_selector_all("a[class*='card-swiper']")
        # 获取 所有 item 第一个 a 标签的 href 属性
        # items = await asyncio.gather(*[item.query_selector("a") for item in items])
        items = await asyncio.gather(*[item.get_attribute("href") for item in items])
        items = [item for item in items if item]  # 去除 None item
        items = ["https://www.adidas.com.hk" + item + "&locale=en_GB" if not item.startswith('http') else item for item in
                 items]
        return items

    # 以下仅适用于 ADIDAS
    async def info_of_item(self, page):
        """
        获取当前商品详情页面的商品信息，包括图像 urls、文本描述
        """
        item_info = {'brand': 'Adidas', }
        # 1. 基础信息 
        # Item 名称 div class="pdp-goods-h en_GB" 的第一个 span
        await page.wait_for_selector("div[class*='pdp-goods-h en_GB']")
        item_name = await page.query_selector("div[class*='pdp-goods-h en_GB']")
        item_name = await item_name.inner_text()
        item_info["item"] = item_name
        # 颜色 div class="color-title"  的第一个 span
        await page.wait_for_selector("div[class*='color-title']")
        color_div = await page.query_selector("div[class*='color-title']")
        color = await color_div.query_selector("span")
        color = await color.inner_text()
        item_info["color"] = color[:color.find("[")].strip()

        # 2. 细节信息
        # 描述段落 div id="navigation-target-description" 下的 第一个 p
        await page.wait_for_selector("div[id='navigation-target-description']")
        description_div = await page.query_selector("div[id='navigation-target-description']")
        description = await description_div.query_selector("p")
        description = await description.inner_text()
        item_info["description"] = description
        # 细节 div class="specifications pc"
        await page.wait_for_selector("div[class*='specifications pc']")
        specifications_div = await page.query_selector("div[class*='specifications pc']")
        bullets = await specifications_div.query_selector("div[class*='bullets']")   # div class="bullets" 下的所有 li
        bullets = await bullets.query_selector_all("li")
        details = []
        for bullet in bullets:
            detail = await bullet.inner_text()
            details.append(detail)
        item_info["details"] = details

        # 3. 图片 div slot="pagination"
        await page.wait_for_selector("div[slot='pagination']")
        pagination_div = await page.query_selector("div[slot='pagination']")
        images = await pagination_div.query_selector_all("img")
        image_links = await asyncio.gather(*[url.get_attribute("src") for url in images])
        image_links = ["https:"+_[:_.rfind("?")] for _ in image_links]
        item_info["image_urls"] = image_links

        # wait for 1s
        await asyncio.sleep(1)

        return item_info


class ZalandoSpider(Spider):
    def __init__(self):
        super().__init__()

    # TODO: 以下仅适用于 Zalando
    async def next_page_btn(self, page):
        """
        获取下一页按钮
        """
        # a title="next page"
        next_page_btn = await page.query_selector("a[title='next page']")
        return next_page_btn

    # TODO: 以下仅适用于 Zalando
    async def id_from_url(self, url):
        # https://en.zalando.de/ulla-popken-maxi-dress-noir-up121c13e-q11.html
        # id : up121c13e-q11  upper
        url = url[:url.rfind('.html')]
        _ = url.split('-')
        return '-'.join(_[-2:]).upper()

    # TODO: 以下仅适用于 Zalando
    async def items_in_page(self, page):
        """
        获取当前页面的所有商品的 url
        """
        # a class="_LM JT3_zV CKDt_l CKDt_l LyRfpJ"
        items = await page.query_selector_all("a[class*='_LM JT3_zV CKDt_l CKDt_l LyRfpJ']")
        # 获取 所有 item 第一个 a 标签的 href 属性
        # items = await asyncio.gather(*[item.query_selector("a") for item in items])
        items = await asyncio.gather(*[item.get_attribute("href") for item in items])
        # 去除 None item 以及不是 https:// 开头的
        items = [item for item in items if item and item.startswith('https://')]
        # 检验 id 长度 KA321C141-Q11, 且倒数第 4 为 -
        ids = await asyncio.gather(*[self.id_from_url(item) for item in items])
        items = [item for item, id_ in zip(items, ids) if len(id_) == 13 and id_[-4] == '-']
        return items

    # TODO: 以下仅适用于 Zalando
    async def info_of_item(self, page):
        """
        获取当前商品详情页面的商品信息，包括图像 urls、文本描述
        """
        item_info = dict()
        # 基础信息 <x-wrapper-re-1-4 re-hydration-id="re-1-4" style="display:block">
        basic_info = await page.query_selector("x-wrapper-re-1-4")
        assert basic_info, "未找到商品详情页的 x-wrapper-re-1-4, 也许页面结构已经改变！"
        # 颜色 span class="sDq_FX lystZ1 dgII7d HlZ_Tf zN9KaA"
        color = await page.query_selector("span[class*='sDq_FX lystZ1 dgII7d HlZ_Tf zN9KaA']")
        # 品牌名 h3 class="FtrEr_ QdlUSH FxZV-M HlZ_Tf _5Yd-hZ"
        brand = await basic_info.query_selector("h3[class*='FtrEr_ QdlUSH FxZV-M HlZ_Tf _5Yd-hZ']")
        # 品类 sapn class="EKabf7 R_QwOV"
        item_category = await basic_info.query_selector("span[class*='EKabf7 R_QwOV']")

        # 如果存在则添加到 item_info 中
        if color:
            item_info["color"] = await color.inner_text()
        if brand:
            item_info["brand"] = await brand.inner_text()
        if item_category:
            item_info["item"] = await item_category.inner_text()

        # 获取item_details中所有
        # 1\ <h5 class="sDq_FX EKH5rj FxZV-M HlZ_Tf">  一级标题
        # 2\ <dt class="sDq_FX lystZ1 dgII7d HlZ_Tf zN9KaA" role="term">Outer fabric material:</dt>  键
        # 3\ <dd class="sDq_FX lystZ1 FxZV-M HlZ_Tf zN9KaA" role="definition">100% polyester</dd> 值
        information = dict()
        btns = await page.query_selector_all(
            "button[class*='_ZDS_REF_SCOPE_ SX0LGY DJxzzA u9KIT8 uEg2FS U_OhzR ZkIJC- Vn-7c- FCIprz heWLCX Wu1CzW "
            "Md_Vex NN8L-8 _d3F40 P3OKTW mo6ZnF K82if3 VWL_Ot HlZ_Tf _13ipK_ LyRfpJ Z1Xqqm _8xiD-i sKmkSN pMa0tB']")
        for btn in btns:
            try:
                await btn.click()
            except Exception as e:
                print(e)
        texts = await page.query_selector_all(
            "h5[class*='sDq_FX EKH5rj FxZV-M HlZ_Tf'], dt[role='term'], dd[role='definition']")
        # 如果是 h5 则作为一级 key，如果是 dt 则作为 key, 如果是 dd 则作为 value
        key_ = None
        key__ = None
        for text in texts:
            if "term" == await text.get_attribute("role"):
                key__ = await text.inner_text()
                information[key_][key__] = []
            elif "definition" == await text.get_attribute("role"):
                value = await text.inner_text()
                information[key_][key__].append(value)
            else:
                key_ = await text.inner_text()
                information[key_] = dict()
        item_info["information"] = information

        # ul aria-label="Product media gallery"
        gallery = await page.query_selector("ul[aria-label='Product media gallery']")
        lis = await gallery.query_selector_all("li")
        urls = await asyncio.gather(*[li.query_selector("img") for li in lis])
        urls = await asyncio.gather(*[url.get_attribute("src") for url in urls])
        urls = [url[:url.find(".jpg") + 4] for url in urls]  # 截取到.jpg
        item_info["image_urls"] = urls

        return item_info


class I24SSpider(Spider):
    def __init__(self, test_mode=False):
        super().__init__(test_mode=test_mode)

    # TODO: 以下仅适用于 XX
    async def next_page_btn(self, page):
        """
        获取下一页按钮
        """
        old_url = page.url
        # https://www.italist.com/cn/women/clothing/coats-jackets/blazers/29/?skip=180
        # 如果有 skip= 则把 skip= 后面的数字加 60
        if old_url.find('skip=') != -1:
            new_url = old_url[:old_url.find('skip=') + 5] + str(int(old_url[old_url.find('skip=') + 5:]) + 60)
        else:
            new_url = old_url + '?skip=60'


        return new_url

    # TODO: 以下仅适用于 24S
    async def id_from_url(self, url):
        # https://www.24s.com/en-hk/izubird-sweatshirt-american-vintage_AMVWFZ4DORA1T1AA00?color=orange
        # id : AMVWFZ4DORA1T1AA00
        code = url[url.rfind('_')+1:url.rfind('?')]
        print(code)
        return code

    # TODO: 以下仅适用于 24S
    async def items_in_page(self, page):
        """
        获取当前页面的所有商品的 url
        """
        # div class="productsList_product-listing-container__e8q1n"
        items_div = await page.query_selector("div[class*='productsList_product-listing-container__e8q1n']")
        assert items_div, "未找到当前类别商品Div class=productsList_product-listing-container__e8q1n, 也许页面结构已经改变！"
        # 获取 items_div 所有class="product_btn__QSoXG"的 a 标签的 href 属性
        items = await items_div.query_selector_all("a[class*='product_btn__QSoXG']")
        items = await asyncio.gather(*[item.get_attribute("href") for item in items])
        items = [item for item in items if item]  # 去除 None item
        # 添加 https://www.italist.com 前缀
        items = ["https://www.24s.com" + item if not item.startswith('http') else item for item in items]
        # ids = await asyncio.gather(*[self.id_from_url(item) for item in items])
        # # 检验 id 长度和格式 : 13238321/13406013
        # items = [item for item, id_ in zip(items, ids) if len(id_) == 17 and id_.find('/') == 8]
        return items

    # TODO: 以下仅适用于 24S
    async def info_of_item(self, page):
        """
        获取当前商品详情页面的商品信息，包括图像 urls、文本描述
        """
        item_info = dict()
        # 基础信息 div class="jsx-1976571714 product-actions-sticky"
        # basic_info = await page.query_selector("div[class*='jsx-1976571714 product-actions-sticky']")
        # assert basic_info, "未找到商品详情页的div class=jsx-1976571714 product-actions-sticky, 也许页面结构已经改变！"
        # # 品牌名 h2 class="jsx-2052347248 brand"
        # brand = await basic_info.query_selector("h2[class*='jsx-2052347248 brand']")
        # # 品类 <h1 class="jsx-2052347248 model">Crewneck Long-sleeved Jumpsuit</h1>
        # item_category = await basic_info.query_selector("h1[class*='jsx-2052347248 model']")
        # # 如果存在则添加到 item_info 中
        # # if color:
        # #     item_info["color"] = await color.inner_text()
        # if brand:
        #     item_info["brand"] = await brand.inner_text()
        # if item_category:
        #     item_info["item"] = await item_category.inner_text()

        # 获取 div class="accordion-text"
        accordion_div = await page.query_selector("div[class*='accordion-text']")
        # li class="m-b-5"
        lis = await accordion_div.query_selector_all("li[class*='m-b-5']")
        for li in lis:
            content = await li.inner_text()
            key_ = content[:(pos := content.find(':'))].strip()
            value = content[pos+1:].strip()
            item_info[key_] = value
        # print(item_info)


        # 获取 carousel_div 所有 img 标签的 src 属性
        # div class ="jsx-2140263580 carousel-item"
        # div class="jsx-1976571714 image-product-info-container"
        img_div = await page.query_selector("div[class*='jsx-1976571714 image-product-info-container']")
        imgs = await img_div.query_selector_all("img")
        urls = await asyncio.gather(*[img.get_attribute("src") for img in imgs])
        # 筛选出 jpg 图片
        urls = [url for url in urls if url and url.endswith('.jpg')]
        item_info["image_urls"] = urls

        return item_info


class LUISAVIAROMASpider(Spider):
    def __init__(self):
        super().__init__()

    # TODO: 以下仅适用于 Luisa Via Roma
    async def next_page_btn(self, page):
        """
        获取下一页按钮
        """
        # a aria-label="Next"
        next_page_btn = await page.query_selector("a[aria-label='Next']")
        return next_page_btn

    # TODO: 以下仅适用于 Luisa Via Roma
    async def id_from_url(self, url):
        # 'https://www.luisaviaroma.cn/en-cn/p/loulou-studio/women/76I-DPO033?ColorId=Q0FNRUw1&lvrid=_p_dDPO_gw'
        #  id = 76I-DPO033
        id_ = url[:url.find('?')]
        id_ = id_[id_.rfind('/')+1:]
        return id_

    # TODO: 以下仅适用于 Luisa Via Roma
    async def items_in_page(self, page):
        """
        获取当前页面的所有商品的 url
        """
        # 获取所有 article 标签 data-id="item"
        items = await page.query_selector_all("article[data-id='item']")
        # 获取 所有 item 第一个 a 标签的 href 属性
        items = await asyncio.gather(*[item.query_selector("a") for item in items])
        items = await asyncio.gather(*[item.get_attribute("href") for item in items])
        items = [item for item in items if item]  # 去除 None item
        # pprint(items)
        items = ["https://www.luisaviaroma.cn" + item if not item.startswith('http') else item for item in
                 items]
        return items

    # TODO: 以下仅适用于 Luisa Via Roma
    async def info_of_item(self, page):
        """
        获取当前商品详情页面的商品信息，包括图像 urls、文本描述
        """
        # 0.图片 Div  data-id="Images"
        image_div = await page.query_selector("div[data-id='Images']")
        images = await image_div.query_selector_all("img")
        image_links = await asyncio.gather(*[url.get_attribute("src") for url in images])
        precessed_links = []
        for i, link in enumerate(image_links):
            link = link.split("images.luisaviaroma.cn/")[1]
            link = link[link.find('/')+1:]
            precessed_links.append("https://images.luisaviaroma.cn/Zoom/" + link)

        # 1.基础信息 div id="item-info" 的
        basic_info_div = await page.query_selector("div[id='item-info']")
        # brand: a data-id="ItemPage-Designer"
        brand = await basic_info_div.query_selector("a[data-id='ItemPage-Designer']")
        brand = await brand.inner_text()
        # item: span data-id="ItemPage-Description"
        item = await basic_info_div.query_selector("span[data-id='ItemPage-Description']")
        item = await item.inner_text()

        # 2.详细信息 ul class="_CESkd1gon1 _1nyEAK7bxg"
        detail_info_ul = await page.query_selector("ul[class*='_CESkd1gon1 _1nyEAK7bxg']")
        # detail_info_ul 所有子节点
        detail_info = await detail_info_ul.query_selector_all("li")
        detail_info_list = []
        for info_item in detail_info:
            info = await info_item.inner_text()
            if len(detail_info_list) != 0 and info in detail_info_list[-1]:
                continue
            detail_info_list.append(info)

        item_info = dict()
        item_info["brand"] = brand
        item_info["item"] = item
        item_info["details"] = detail_info_list
        item_info["image_urls"] = precessed_links
        return item_info


class NetAPorterSpider(Spider):
    def __init__(self):
        super().__init__()

    # 以下仅适用于 Net-A-Porter
    async def next_page_btn(self, page):
        """
        获取下一页按钮
        """
        # a class="Pagination7__next"
        next_page_btn = await page.query_selector("a[class*='Pagination7__next']")
        # 且不是 class="Pagination7__next Pagination7__next--disabled"
        class_ = await next_page_btn.get_attribute("class")
        if "Pagination7__next--disabled" in class_:
            return None
        return next_page_btn

    # 以下仅适用于 Net-A-Porter
    async def id_from_url(self, url):
        # https://www.net-a-porter.com/en-jp/shop/product/off-white/clothing/casual-jackets/belted-cotton-twill-jacket/1647597310972290
        return url[url.rfind('/')+1:]

    # 以下仅适用于 ADIDAS
    async def items_in_page(self, page):
        """
        获取当前页面的所有商品的 url
        """
        # 获取所有 div class="ProductList0__productItemContainer"
        items = await page.query_selector_all("div[class*='ProductList0__productItemContainer']")
        # 获取 所有 item 第一个 a 标签的 href 属性
        items = await asyncio.gather(*[item.query_selector("a") for item in items])
        items = await asyncio.gather(*[item.get_attribute("href") for item in items])
        items = [item for item in items if item]  # 去除 None item
        items = ["https://www.net-a-porter.com" + item if not item.startswith('http') else item for item in
                 items]
        return items

    # 以下仅适用于 Net-A-Porter
    async def info_of_item(self, page):
        """
        获取当前商品详情页面的商品信息，包括图像 urls、文本描述
        """
        item_info = {}
        # 1. 基础信息 
        # brand h1 itemprop="brand"
        await page.wait_for_selector("h1[itemprop='brand']")
        brand = await page.query_selector("h1[itemprop='brand']")
        item_info["brand"] = await brand.inner_text()
        # Item 名称 p class="ProductInformation87__name"
        await page.wait_for_selector("p[class*='ProductInformation87__name']")
        item_name = await page.query_selector("p[class*='ProductInformation87__name']")
        item_name = await item_name.inner_text()
        item_info["item"] = item_name
        # 颜色 span class="ProductDetailsColours87__colourName"
        await page.wait_for_selector("span[class*='ProductDetailsColours87__colourName']")
        color_div = await page.query_selector("span[class*='ProductDetailsColours87__colourName']")
        color = await color_div.inner_text()
        item_info["color"] = color
        # print(item_info)
        # 2. 细节信息
        # 描述段落 div class="EditorialAccordion87__accordionContent EditorialAccordion87__accordionContent--editors_notes"
        # 点击 div id="EDITORS_NOTES"
        # await page.click("div[id='EDITORS_NOTES']")
        await page.wait_for_selector("div[class*='EditorialAccordion87__accordionContent EditorialAccordion87__accordionContent--editors_notes']")
        description_div = await page.query_selector("div[class*='EditorialAccordion87__accordionContent EditorialAccordion87__accordionContent--editors_notes']")
        description = await description_div.query_selector("p")
        description = await description.inner_text()
        item_info["editors_notes"] = description
        # print(item_info)
        # size&fit div class="EditorialAccordion87__accordionContent EditorialAccordion87__accordionContent--size_and_fit"
        # 点击 div id="SIZE_AND_FIT"
        await page.click("div[id='SIZE_AND_FIT']")
        await page.wait_for_selector("div[class*='EditorialAccordion87__accordionContent EditorialAccordion87__accordionContent--size_and_fit']")
        size_fit_div = await page.query_selector("div[class*='EditorialAccordion87__accordionContent EditorialAccordion87__accordionContent--size_and_fit']")
        size_fit = await size_fit_div.inner_text()
        item_info["size_fit"] = size_fit
        # 细节 div class="EditorialAccordion87__accordionContent EditorialAccordion87__accordionContent--details_and_care"
        # 点击 div id="DETAILS_AND_CARE"
        await page.click("div[id='DETAILS_AND_CARE']")
        await page.wait_for_selector("div[class*='EditorialAccordion87__accordionContent EditorialAccordion87__accordionContent--details_and_care']")
        specifications_div = await page.query_selector("div[class*='EditorialAccordion87__accordionContent EditorialAccordion87__accordionContent--details_and_care']")
        bullets = await specifications_div.query_selector_all("li")
        details = []
        for bullet in bullets:
            detail = await bullet.inner_text()
            details.append(detail)
        item_info["details"] = details

        # 3. 图片 div class="ImageCarousel87__thumbnails ProductDetailsPage87__imageCarouselThumbnails"
        await page.wait_for_selector("div[class*='ImageCarousel87__thumbnails ProductDetailsPage87__imageCarouselThumbnails']")
        pagination_div = await page.query_selector("div[class*='ImageCarousel87__thumbnails ProductDetailsPage87__imageCarouselThumbnails']")
        images = await pagination_div.query_selector_all("img")
        image_links = await asyncio.gather(*[url.get_attribute("src") for url in images])
        image_links = ["https:"+_ for _ in image_links]
        item_info["image_urls"] = image_links

        # wait for 1s
        await asyncio.sleep(1)

        return item_info



async def test_function(url):
    # semaphore = asyncio.Semaphore(1)
    # async with semaphore:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False, args=[])#'--start-maximized'])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            locale="en-GB",  # zh-CN、en-GB
            no_viewport=True
        )
        # 拦截 webp
        abort_types = ['media', 'font', "image"] #'stylesheet']
        await context.route("**/*", lambda
            route: route.abort() if route.request.resource_type in abort_types else route.continue_())
        page = await context.new_page()
        # await page.route("**/*.{png,jpg,jpeg}", lambda route: route.abort())  # 禁止加载图片
        await page.goto(url, wait_until='domcontentloaded')
        # await page.wait_for_url(url)
        # 下面是你想要测试的代码
        spider = NetAPorterSpider()

        # pprint(await spider.info_of_item(page))
        pprint(await spider.items_in_page(page))
        # print(await spider.id_from_url(url))

if __name__ == '__main__':
    # Test
    # asyncio.run(
    #     test_function("https://www.net-a-porter.com/en-jp/shop/new-in/clothing")
    # )

    loop = asyncio.get_event_loop()
    spider_map = {
        'yoox': [YOOXSpider, 'Meta/YOOX-Meta', 'category-json/yoox_category.json'],
        'farfetch': [FARFETCHSpider, 'Meta/FARFETCH-Meta', 'category-json/farfetch_category-convert.json'],
        'italist': [ItalistSpider, 'Meta/Italist-Meta', 'category-json/italist_category.json'],
        'luisaviaroma': [LUISAVIAROMASpider, 'Meta/LUISAVIAROMA-Meta', 'category-json/LUISAVIAROMA_category.json'],
        'adidas': [ADIDASSpider, 'Meta/ADIDAS-Meta', 'category-json/adidas_category.json'],
        'netaporter': [NetAPorterSpider, 'Meta/NetAPorter-Meta', 'category-json/net-a-porter_category.json'],
    }

    platform = 'luisaviaroma'
    platform = 'farfetch'
    platform = 'adidas'
    platform = 'yoox'
    platform = 'netaporter'

    spider = spider_map[platform][0]()
    loop.run_until_complete(
        spider.async_run(spider_map[platform][1], spider_map[platform][2], concurrency=4, headless=False)
    )

    pass
