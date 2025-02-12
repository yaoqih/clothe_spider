import json
import os
import time

import jsonlines
from jsmin import jsmin
from selenium.webdriver.chrome.options import Options
import requests

# 创建连接池
session = requests.Session()
session.mount('http://', requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=20, max_retries=3))
proxies = {
    "http": None,
    # "http": "58.255.6.38:9999",
    "https": None
}


def traverse_all_file(folder, postfix=None):
    """
    遍历文件夹下所有文件
    :param folder: 文件夹路径
    :param postfix: 后缀名
    :return: 文件路径
    """
    file_list = []
    for root, dirs, files in os.walk(folder):
        for file in files:
            if postfix is None:
                file_list.append(os.path.join(root, file))
            elif file.endswith(postfix):
                file_list.append(os.path.join(root, file))
    return file_list


def jsonl_add(jsonl_file, item: dict):
    with jsonlines.open(jsonl_file, mode='a') as writer:
        writer.write(item)


def jsonl_read(jsonl_file: str) -> list:
    assert os.path.isfile(jsonl_file), f"{jsonl_file} not exist"
    with jsonlines.open(jsonl_file) as reader:
        return [item for item in reader]


def read_json(json_file):
    assert os.path.isfile(json_file), f"{json_file} not exist"
    with open(json_file, "r") as f:
        min_f = jsmin(f.read())
        return json.loads(min_f)


# 进度条
def progress_bar(prefix, i, n):
    """
    :param prefix: 输出前缀
    :param i: 当前位置
    :param n: 总个数
    :return:
    """
    percent = int((i + 1) * 100 / n)
    print("\r%s |%s%s|[%d/%d %3d%%]" % (prefix, '>' * int(percent / 5), ' ' * (20 - int(percent / 5)),
                                        i + 1, n, percent), end="", flush=True)


def get_proxy():
    return "http://117.26.41.173:8888"
    # ip_port = requests.get(
    #     "http://proxy.siyetian.com/apis_get.html?token=gHbi1iTqNWMORVU14kaVVjTR1STqFUeNpXQy0kaNNjTEFEMNR0Zz4keVl3TElEM.AO0QzMyUzN4YTM&limit=1&type=0&time=&split=1&split_text=&repeat=0&isp=0").text
    # return f"http://{ip_port}"


def browser_scroll(browser, times: int = 10, sleep_time: float = 0.5):
    for i in range(times):
        browser.execute_script('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(sleep_time)


def chrome_options(headless=True):
    opt = Options()
    opt.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})  # forbid img loading
    opt.add_experimental_option('excludeSwitches', ['enable-automation'])  # No automation head
    opt.add_argument('window-size=1920, 1080')
    # opt.add_argument('--start-maximized')
    if headless:
        opt.add_argument("user-agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/110.0.0.0 Safari/537.36'")
        opt.add_argument('--headless')
    # if use_proxy:
    #     opt.add_argument('--proxy-server=%s' % get_proxy())
    return opt


class code_recoder:
    def __init__(self, dict_txt, todo_txt):
        self.dict_txt, self.todo_txt = dict_txt, todo_txt
        self.dict = self.read_codes(dict_txt)
        if not os.path.isfile(todo_txt):
            os.makedirs(todo_txt)
        self.todo = self.read_codes(todo_txt)

    def get_todo_code(self):
        return self.todo[0]

    def dict_append_code(self, code):
        self.dict.append(code)
        self.todo.remove(code)
        self.save_codes(self.dict, self.dict_txt)
        self.save_codes(self.todo, self.todo_txt)

    def update_todo(self, codes):
        for c in codes:
            if c not in self.dict and c not in self.todo:
                self.todo.append(c)
        self.save_codes(self.todo, self.todo_txt)

    def read_codes(self, txt):
        with open(txt, "r") as f:  # 打开文件
            codes = f.read().split(" ")
            f.close()
        return codes

    def save_codes(self, codes, txt):
        codes_str = ' '.join(codes)
        with open(txt, "w") as f:
            f.write(codes_str)
            f.close()


def read_codes_from_txt(txt):
    if not os.path.isfile(txt):
        return []
    with open(txt, "r") as f:  # 打开文件
        codes = f.read().split(" ")
        f.close()
    while "" in codes:
        codes.remove("")
    return codes


# 读取已获取的codes
def read_codebook(txt):
    with open(txt, "r") as f:
        exist = f.read()
        return exist.split(" ")


# 保存单个code
def save_code_to_txt(code, txt):
    with open(txt, "a") as f:
        f.write(" " + code)
    # print("%s添加code：%s" % (txt, code))


# 下载url中的图片
def download_image(image_url, filename, dst):
    r = requests.get(image_url, proxies=proxies)
    if r.status_code == 200:
        with open(dst + "/" + filename, 'wb') as fp:
            fp.write(r.content)
            fp.close()
        return True
    return False


# 检查是否重复
def check_repeat(code, txt):
    # 读取codes.txt，并用列表codes记录
    with open(txt, "r") as f:  # 打开文件
        exist = f.read()
    codes = exist.split(" ")
    if code in codes:
        return True
    return False


# 去除urls中与txt重复（需提供url获取code的方法）
def remove_repeat(urls, txt, get_code_from_url):
    # 读取codes.txt，并用列表codes记录
    with open(txt, "r") as f:  # 打开文件
        exist = f.read()
    codes = exist.split(" ")
    # 去除之前已经获取过的code
    new = []
    for u in urls:
        ucode = get_code_from_url(u)
        if ucode not in codes and ucode.find('-') != -1:
            new.append(u)
    return new

# 统计某一文件夹（递归）下所有 jsonl 文件的行数
def count_jsonl_lines(folder):
    total = 0
    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.endswith("jsonl"):
                with open(os.path.join(root, file), "r", encoding='gb18030', errors='ignore') as f:
                    for line in f:
                        total += 1
    return total

if __name__ == '__main__':
    # download_image("https://www.revolvecn888.com/images/p4/n/z/COEL-WQ95_V7.jpg", "COEL-WQ95-7.jpg", "revolve")
    # print(get_proxy())
    print("YOOX:", count_jsonl_lines("YOOX-Meta"))
    print("FARFETCH:", count_jsonl_lines("FARFETCH-Meta"))