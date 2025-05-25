import sys
from pathlib import Path
import json
import os

import fitz
from iiif import IIIFStatic
from iiif_prezi.factory import ManifestFactory

# 修改输出路径为 docs 目录
extract_path = Path("./output/images")  # 保留临时提取图像的路径
image_path = Path("./docs/images")  # 改为 docs/images
manifest_path = Path("./docs")  # 改为 docs


def ensure_dirs():
    """Construct output dirs"""
    extract_path.mkdir(parents=True, exist_ok=True)
    image_path.mkdir(parents=True, exist_ok=True)
    manifest_path.mkdir(parents=True, exist_ok=True)


def extract_images_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    image_count = 0

    images = []
    for i in range(len(doc)):
        page_num = i + 1
        print(f"extracting images from page {page_num}..")

        page = doc.load_page(i)
        count_per_page = 1
        for img in page.get_images():
            xref = img[0]
            pix = fitz.Pixmap(doc, xref)
            target_out = Path(extract_path, f"{image_count:02}.png")

            if pix.n - pix.alpha < 4:  # this is GRAY or RGB
                pix.save(str(target_out))
            else:  # CMYK: convert to RGB first
                pix = fitz.Pixmap(fitz.csRGB, pix)
                pix.save(str(target_out))
            pix = None

            images.append(target_out)

            count_per_page = count_per_page + 1
            image_count = image_count + 1

    print(f"finished extracting {image_count} images")
    return images


def generate_iiif(images, pdf, base_url="http://localhost:8000"):
    """Generate IIIF 2.0 static image-service and manifest"""

    # configure manifest factory
    manifest_factory = ManifestFactory()
    manifest_factory.set_base_prezi_dir(str(manifest_path))
    manifest_factory.set_base_prezi_uri(base_url)
    manifest_factory.set_base_image_uri(f"{base_url}/images")
    manifest_factory.set_iiif_image_info(2.0, 1)

    manifest = manifest_factory.manifest(label="Example Manifest from PDF")
    manifest.description = "Sample P2 manifest with images from PDF"
    manifest.set_metadata({"Generated from": pdf})

    # configure tile generator for static assets
    tile_generator = IIIFStatic(dst=str(image_path),
                                prefix=f"{base_url}/images",
                                tilesize=512,
                                api_version="2.1",
                                extras=['/full/90,/0/default.jpg',
                                        '/full/200,/0/default.jpg'])  # thumbnail for UV

    seq = manifest.sequence()
    idx = 0
    for i in images:
        print(f"processing image {idx}")
        image_id = i.stem

        # create a canvas with an annotation
        canvas = seq.canvas(ident=image_id, label=f"Canvas {idx}")

        # create an annotation on the Canvas
        annotation = canvas.annotation(ident=f"page-{idx}")

        # add an image to the anno
        img = annotation.image(image_id, iiif=True)
        img.service.profile = 'http://iiif.io/api/image/2/level0.json'

        # set image + canvas hw
        img.set_hw_from_file(str(i))
        canvas.height = img.height
        canvas.width = img.width

        # generate image-pyramid
        tile_generator.generate(src=i, identifier=image_id)

        idx = idx + 1

    manifest.toFile(compact=False)


# 从 update_iiif_urls.py 移植的 URL 更新功能
def update_json_data(data, old_base, new_base):
    """
    递归更新 JSON 数据结构中的字符串。
    如果字符串以 old_base 开头，则将其替换为 new_base。
    """
    if isinstance(data, dict):
        return {k: update_json_data(v, old_base, new_base) for k, v in data.items()}
    elif isinstance(data, list):
        return [update_json_data(elem, old_base, new_base) for elem in data]
    elif isinstance(data, str):
        if data.startswith(old_base):
            return new_base + data[len(old_base):]
    return data


def process_json_file(file_path, old_base, new_base):
    """
    读取、更新并写回单个 JSON 文件。
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        
        updated_content = update_json_data(content, old_base, new_base)
        
        # 检查内容是否有实际变化，避免不必要的写操作
        if json.dumps(content) != json.dumps(updated_content):
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(updated_content, f, ensure_ascii=False, indent=2)
            print(f"Updated: {file_path}")
        else:
            print(f"No changes needed: {file_path}")

    except FileNotFoundError:
        print(f"Error: File not found - {file_path}")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON - {file_path}")
    except Exception as e:
        print(f"An unexpected error occurred with {file_path}: {e}")


def update_urls_in_docs(old_base_url, new_base_url):
    """更新 docs 目录中的 URL"""
    docs_root_dir = "./docs"
    
    print(f"Starting URL update process...")
    print(f"Replacing '{old_base_url}' with '{new_base_url}'")
    print(f"Processing files in and under: {docs_root_dir}\n")

    # 处理 manifest.json 文件
    files_to_process = ["manifest.json"]
    for file_name in files_to_process:
        abs_file_path = os.path.join(docs_root_dir, file_name)
        if os.path.isfile(abs_file_path):
            print(f"Processing file: {abs_file_path}")
            process_json_file(abs_file_path, old_base_url, new_base_url)
        else:
            print(f"Warning: Specified file not found - {abs_file_path}")
    
    print("\n--- Processing directories ---")
    # 处理 images 目录中的所有 .json 文件
    dirs_to_process = ["images"]
    for dir_name in dirs_to_process:
        abs_dir_path = os.path.join(docs_root_dir, dir_name)
        if os.path.isdir(abs_dir_path):
            print(f"Scanning directory: {abs_dir_path}")
            for root, _, files in os.walk(abs_dir_path):
                for file in files:
                    if file.endswith(".json"):
                        json_file_path = os.path.join(root, file)
                        print(f"Processing file: {json_file_path}")
                        process_json_file(json_file_path, old_base_url, new_base_url)
        else:
            print(f"Warning: Specified directory not found - {abs_dir_path}")
            
    print("\nURL update process finished.")


def read_github_url_from_home_txt():
    """从 home.txt 文件读取 GitHub Pages URL"""
    home_txt_path = "./docs/home.txt"
    try:
        with open(home_txt_path, 'r', encoding='utf-8') as f:
            url = f.readline().strip()
            if url:
                # 确保 URL 以斜杠结尾
                if not url.endswith('/'):
                    url += '/'
                return url
            else:
                print(f"Warning: {home_txt_path} is empty.")
                return None
    except FileNotFoundError:
        print(f"Warning: {home_txt_path} not found. Using default URL.")
        return None
    except Exception as e:
        print(f"Error reading {home_txt_path}: {e}")
        return None


if __name__ == '__main__':
    if pdf := sys.argv[-1]:
        ensure_dirs()
        
        # 从 home.txt 读取 GitHub Pages URL
        github_url = read_github_url_from_home_txt()
        
        # 使用默认 URL 生成 IIIF 资源
        placeholder_url = "http://localhost:8000"
        
        images = extract_images_from_pdf(pdf)
        generate_iiif(images, pdf, placeholder_url)
        
        # 如果成功读取了 GitHub Pages URL，则更新所有 URL
        if github_url:
            update_urls_in_docs(placeholder_url, github_url)
        
        print("完成！IIIF 资源已生成到 ./docs 目录，并已更新所有 URL。")
    else:
        print("请提供 PDF 文件路径作为参数")
