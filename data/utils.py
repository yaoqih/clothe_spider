import json
import math
import os
import shutil

import yaml

from tqdm import tqdm


def write_yaml(data: dict, file_name: str):
    with open(file_name, 'w') as yaml_file:
        yaml.dump(data, yaml_file, default_flow_style=False)


def list_all_item_jsonl(root: str):
    assert os.path.isdir(root), f"{root} is not a directory"
    jsonl_files = []
    for root, dirs, files in os.walk(root):
        for file in files:
            if file.endswith("items.jsonl"):
                jsonl_files.append((root, file))
    return jsonl_files


def read_jsonl(file_name: str):
    json_objects = []
    with open(file_name, 'r', encoding='utf-8') as jsonl_file:
        for line in jsonl_file:
            json_obj = json.loads(line)
            json_objects.append(json_obj)
    return json_objects


def read_json_as_dict(file_name: str):
    with open(file_name, 'r') as json_file:
        json_dict = json.load(json_file)
    return json_dict


# 将整个文件夹下移动到另一个文件夹下
def move_folder(src, dst):
    if not os.path.exists(dst):
        os.mkdir(dst)
    else:
        print(f"Warning: {dst} already exists, will be skipped")
    shutil.move(src, dst)


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


def read_txt_as_lines(file_name: str):
    with open(file_name, 'r') as txt_file:
        lines = txt_file.readlines()
    return lines


if __name__ == '__main__':
    print(len(scan_files_in_dir("/data1/chongzheng")))
    pass
