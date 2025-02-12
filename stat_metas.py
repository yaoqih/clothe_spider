import os
from data.data_stat import stat_meta_folder
meta_root = "D:\Spider\Meta"
total_items = 0
total_images = 0
for sub_dir in os.listdir(meta_root):
    if sub_dir.endswith("Meta"):
        meta_path = os.path.join(meta_root, sub_dir)
        items, images = stat_meta_folder(meta_path)
        total_items += items
        total_images += images

print(total_items, total_images)

