import json
import os

from tqdm import tqdm


def scan_files_in_dir(directory, postfix: set[str] = None, progress_bar: tqdm = None) -> list:
    """
    递归遍历目录及其子目录，返回所有文件的路径
    采用 os.scandir() 代替 os.listdir()，可以提高遍历速度
    :param directory: 需要遍历的目录
    :param postfix: 可接受的文件后缀名列表
    :param progress_bar: 进度条，用于同步递归的进度
    :return: 文件 entry 列表
    """
    file_list = []
    progress_bar = tqdm(total=0, desc=f"Scanning", ncols=100) if progress_bar is None else progress_bar
    for entry in os.scandir(directory):
        if entry.is_file():
            if postfix is None or os.path.splitext(entry.path)[1] in postfix:
                file_list.append(entry)
                progress_bar.total += 1
                progress_bar.update(1)
        elif entry.is_dir():
            file_list += scan_files_in_dir(entry.path, postfix=postfix, progress_bar=progress_bar)  # 递归遍历子目录
    return file_list



def stat_meta_folder(meta_folder):
    """
    统计 meta 文件夹中的文件数量
    :param meta_folder: meta 文件夹路径
    :return: 文件数量
    """
    # 查找 meta 文件夹下所有 items.jsonl 文件
    items = scan_files_in_dir(meta_folder, postfix={'.jsonl'})
    # 统计 items.jsonl 文件中的 item 数量 (每个 item 为一行)
    num_items = 0
    num_images = 0
    for item in items:
        with open(item.path, 'r', encoding='utf-8') as jsonl_file:
            for line in jsonl_file:
                num_items += 1
                # 将 line 转换成 dict
                item_dict = json.loads(line)
                # 获取 dict 中包含‘image’的键值对的长度
                for key, value in item_dict.items():
                    if 'image' in key and isinstance(value, list):
                        num_images += len(value)
                        break
    print(f"{meta_folder}: {num_items:,} / {num_images:,}")
    # print(f"Found } images in {meta_folder}")

    return num_items, num_images



if __name__ == '__main__':
    for sub_folder in os.listdir('D:\Spider\Meta'):
        stat_meta_folder(os.path.join('D:\Spider\Meta', sub_folder))
    pass
