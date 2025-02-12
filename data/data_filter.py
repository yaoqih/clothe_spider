import json
import os

from tqdm import tqdm

from data.utils import read_jsonl


def clean_yoox_meta():
    meta_root = os.path.join("Meta","YOOX-Meta")
    dst_root = os.path.join("Meta", "YOOX-Meta-Clean")
    assert os.path.exists(meta_root), f"{meta_root} not exists!"

    progress = tqdm(desc="items", total=0)
    for gender in os.scandir(meta_root):
        if gender.is_dir():
            for cate in os.scandir(gender.path):
                if cate.is_dir():
                    for gory in os.scandir(cate.path):
                        item_jsonl = os.path.join(gory.path, "items.jsonl")
                        try:
                            meta_data = read_jsonl(item_jsonl)
                        except Exception as e:
                            print(f"Error: {e}")
                            continue

                        dst_item_jsonl = item_jsonl.replace(meta_root, dst_root)
                        if not os.path.exists(os.path.dirname(dst_item_jsonl)):
                            os.makedirs(os.path.dirname(dst_item_jsonl))

                        with open(dst_item_jsonl, 'a') as jsonl_file:
                            for item in meta_data:
                                if "image_urls" in item:
                                    json_string = json.dumps(item)
                                    jsonl_file.write(json_string + '\n')
                                    progress.total += 1
                                    progress.update(1)


if __name__ == '__main__':
    clean_yoox_meta()
