from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageOps
from pyzbar.pyzbar import ZBarSymbol, decode


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

BASE_DIR = Path(__file__).resolve().parent


class ExtractError(Exception):
    pass


def normalize_isbn(text: str) -> str | None:
    cleaned = re.sub(r"[^0-9Xx]", "", str(text or "")).upper()
    if len(cleaned) in {10, 13}:
        return cleaned
    return None


def iter_image_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        [path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS],
        key=lambda item: item.name.lower(),
    )


def build_candidate_images(image: Image.Image) -> list[Image.Image]:
    base = ImageOps.exif_transpose(image).convert("RGB")
    candidates: list[Image.Image] = []
    for rotated in (base, base.rotate(90, expand=True), base.rotate(180, expand=True), base.rotate(270, expand=True)):
        gray = ImageOps.grayscale(rotated)
        high_contrast = ImageOps.autocontrast(gray)
        candidates.extend(
            [
                rotated,
                gray,
                high_contrast,
                gray.resize((max(1, gray.width * 2), max(1, gray.height * 2))),
                high_contrast.resize((max(1, high_contrast.width * 2), max(1, high_contrast.height * 2))),
            ]
        )
    return candidates


def decode_isbn_from_image(image_path: Path) -> str:
    try:
        with Image.open(image_path) as image:
            candidates = build_candidate_images(image)
    except Exception as exc:
        raise ExtractError(f"图片打开失败: {exc}") from exc

    symbols = [ZBarSymbol.EAN13, ZBarSymbol.UPCA, ZBarSymbol.CODE128]
    for candidate in candidates:
        try:
            results = decode(candidate, symbols=symbols)
        except KeyboardInterrupt:
            raise
        except Exception:
            continue
        for item in results:
            isbn = normalize_isbn(item.data.decode("utf-8", errors="ignore"))
            if isbn:
                return isbn
    raise ExtractError("未识别到有效 ISBN 条形码")





def process_images(image_files: list[Path], verbose: bool = False) -> list[tuple[str, str | None]]:
    """处理图片文件列表，返回结果列表，识别成功的图片将被删除"""
    results = []
    try:
        for idx, image_path in enumerate(image_files, start=1):
            try:
                isbn = decode_isbn_from_image(image_path)
                results.append((image_path.name, isbn))
                status = "SUCCESS"
                detail = f"ISBN={isbn}"
                
                # 识别成功，删除图片文件
                try:
                    image_path.unlink()
                    detail += " (图片已删除)"
                except OSError as exc:
                    detail += f" (图片删除失败: {exc})"
                    
            except ExtractError as exc:
                results.append((image_path.name, None))
                status = "FAILED"
                detail = str(exc) + " (图片保留)"
            except KeyboardInterrupt:
                print(f"\n用户中断，已处理 {idx-1} 张图片")
                raise
            
            # 总是显示进度，即使没有 verbose
            if verbose:
                print(f"[{idx}/{len(image_files)}] {status} {image_path.name} {detail}")
            else:
                # 非详细模式下，每10张图片显示一次进度
                if idx % 10 == 0 or idx == len(image_files):
                    print(f"已处理 {idx}/{len(image_files)} 张图片...")
    
    except KeyboardInterrupt:
        print("\n处理被用户中断")
        return results
    
    return results


def save_results(results: list[tuple[str, str | None]], output_path: Path) -> bool:
    """保存结果到文件"""
    try:
        with output_path.open("w", encoding="utf-8") as f:
            for filename, isbn in results:
                if isbn:
                    f.write(f"{filename}: {isbn}\n")
                else:
                    f.write(f"{filename}: NOT_FOUND\n")
        return True
    except OSError as exc:
        print(f"无法写入输出文件 {output_path}: {exc}", file=sys.stderr)
        return False


def main() -> int:
    # 默认设置
    image_dir = BASE_DIR / "未入库"
    output_path = BASE_DIR / "ISBN.txt"
    
    # 检查图片目录
    image_files = iter_image_files(image_dir)
    if not image_files:
        print(f"未找到图片文件: {image_dir}", file=sys.stderr)
        return 1
    
    total_images = len(image_files)
    print(f"在 '{image_dir}' 中找到 {total_images} 张图片")
    print()
    
    # 初始化默认值
    limit = 0
    verbose = False
    
    # 显示菜单
    while True:
        print("=" * 50)
        print("请选择处理模式:")
        print("1. 处理全部图片（默认）")
        print("2. 只处理前 N 张图片")
        print("3. 启用详细模式处理全部图片")
        print("4. 退出")
        print("=" * 50)
        
        try:
            choice = input("请输入选择 (1-4): ").strip()
            if not choice:
                choice = "1"  # 默认选择1
            
            if choice == "1":
                limit = 0
                verbose = False
                break
            elif choice == "2":
                while True:
                    try:
                        limit_input = input(f"请输入要处理的图片数量 (1-{total_images}): ").strip()
                        if not limit_input:
                            print("使用默认值: 10")
                            limit = 10
                        else:
                            limit = int(limit_input)
                        
                        if 1 <= limit <= total_images:
                            break
                        else:
                            print(f"请输入 1 到 {total_images} 之间的数字")
                    except ValueError:
                        print("请输入有效的数字")
                verbose = False
                break
            elif choice == "3":
                limit = 0
                verbose = True
                break
            elif choice == "4":
                print("退出程序")
                return 0
            else:
                print("无效的选择，请重新输入")
        except KeyboardInterrupt:
            print("\n退出程序")
            return 0
    
    # 应用数量限制
    if limit > 0:
        image_files = image_files[:limit]
        print(f"将处理前 {limit} 张图片")
    
    print(f"开始处理 {len(image_files)} 张图片...")
    print("注意：识别成功的图片将被删除，识别失败的图片将保留在原目录中。")
    if verbose:
        print("详细模式已启用")
    
    # 处理图片
    results = process_images(image_files, verbose)
    
    if not results:
        print("没有处理任何图片")
        return 1
    
    # 保存结果
    if save_results(results, output_path):
        # 统计信息
        success_count = sum(1 for _, isbn in results if isbn)
        failed_count = len(results) - success_count
        print(f"处理完成: 成功识别 {success_count} 张图片（已删除），失败 {failed_count} 张图片（保留在原目录中）")
        print(f"ISBN识别结果已保存到: {output_path}")
        return 0 if failed_count == 0 else 1
    else:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())