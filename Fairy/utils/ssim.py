import cv2
import numpy as np


def load_image(image_path):
    return cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)  # 转为灰度图


def calculate_pixel_diff(image1, image2):
    # 计算两张图像的绝对差异
    diff = cv2.absdiff(image1, image2)
    non_zero_diff = np.count_nonzero(diff)  # 计算非零差异的像素数
    return non_zero_diff


def is_significant_difference(image1_path, image2_path, threshold=10000):
    # 加载图片
    image1 = load_image(image1_path)
    image2 = load_image(image2_path)

    # 计算像素差异
    diff_count = calculate_pixel_diff(image1, image2)

    print(f"非零差异的像素数量: {diff_count}")

    if diff_count > threshold:
        return True  # 有显著差异
    else:
        return False  # 没有显著差异


# 示例使用
# image1_path = './screenshot/2025-04-15_16-29-27-1.png'
# image2_path = './screenshot/2025-04-15_16-29-39-2.png'
# image3_path = './screenshot/2025-04-15_16-29-39-3.png'
# i4_path = './screenshot/2025-04-15_16-29-49-4.png'
#
# i7_path = './screenshot/2025-04-15_16-31-27-7.png'
# i8_path = './screenshot/2025-04-15_16-31-28-8.png'
#
# if is_significant_difference(image1_path, image2_path):
#     print("图片不同，可以保留")
# else:
#     print("图片没有显著差异，可以去重")
