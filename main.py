import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from utils.MsgNotifier import send_notification
import requests

from utils.YamlReader import YamlReader


def login_to_novelia(username: str, password: str):
    url = "https://auth.novelia.cc/api/v1/auth/login"

    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "referer": "https://auth.novelia.cc/"
    }

    data = {
        "app": "n",
        "username": username,
        "password": password
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=data
        )

        if response.status_code != 200:
            print(f"登录失败，状态码: {response.status_code}，响应内容: {response.text}")
            return None

        return response.text

    except requests.exceptions.RequestException as e:
        print(f"请求错误: {e}")
        return None


def get_all_favorite_wenku_books(token: str, delay: float = 0.5) -> Optional[List[Dict]]:
    """
    获取用户所有收藏的文库书籍列表（自动翻页）

    Args:
        token: 认证token
        delay: 请求间隔延迟（秒），避免请求过快

    Returns:
        包含所有文库书籍信息的列表，每个元素包含wenkuId, titleJp, titleZh, createAt
    """
    all_books = []
    book_ids = []
    page = 0
    page_size = 24

    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {token}",
        "referer": "https://n.novelia.cc/favorite/wenku/default?page=1&selected=1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    while True:
        try:
            # 构建请求URL和参数
            params = {
                "page": page,
                "pageSize": page_size,
                "sort": "create"
            }

            print(f"\n正在请求文库第 {page + 1} 页...")

            response = requests.get(
                "https://n.novelia.cc/api/user/favored-wenku/default",
                params=params,
                headers=headers,
                timeout=30  # 设置超时时间
            )

            # 检查响应状态
            if response.status_code != 200:
                print(f"请求失败，状态码: {response.status_code}")
                break

            # 解析JSON响应
            data = response.json()

            # 检查是否有数据
            items = data.get("items", [])
            if not items:
                print("没有更多数据")
                break

            # 提取需要的字段
            for item in items:
                book_ids.append(item.get("id", ""))

            print(f"文库第 {page + 1} 页获取到 {len(items)} 条记录，总计 {len(book_ids)} 条")

            # 如果返回的数据少于page_size，说明是最后一页
            if len(items) < page_size:
                print("已获取所有文库数据")
                break

            # 翻到下一页
            page += 1

            # 添加延迟，避免请求过快
            if delay > 0:
                time.sleep(delay)

        except requests.exceptions.Timeout:
            print(f"文库第 {page + 1} 页请求超时")
            break
        except requests.exceptions.RequestException as e:
            print(f"文库第 {page + 1} 页网络请求错误: {e}")
            break
        except ValueError as e:
            print(f"文库第 {page + 1} 页JSON解析错误: {e}")
            break
        except Exception as e:
            print(f"文库第 {page + 1} 页发生未知错误: {e}")
            break

    # 获取每本小说的详细信息
    for i, novel_id in enumerate(book_ids):
        try:
            print(f"正在获取第 {i + 1}/{len(book_ids)} 本小说详情 (ID: {novel_id})...")
            headers["referer"] = f"https://n.novelia.cc/wenku/{novel_id}"
            url = f"https://n.novelia.cc/api/wenku/{novel_id}"

            response = requests.get(
                url,
                headers=headers,
                timeout=30
            )

            # 检查响应状态
            if response.status_code != 200:
                continue

            # 解析JSON响应
            data = response.json()

            # 提取需要的字段
            novel_info = {
                "novelId": novel_id,
                "titleJp": data.get("title", ""),
                "titleZh": data.get("titleZh", ""),
                "updateAt": data.get("latestPublishAt", 0)
            }

            all_books.append(novel_info)

        except Exception as e:
            print(f"获取小说详情时发生错误 (ID: {novel_id}): {e}")
            continue

        # 添加延迟，避免请求过快
        if i < len(book_ids) - 1 and delay > 0:
            time.sleep(delay)

    return all_books


def get_all_favorite_web_books(token: str, delay: float = 0.5) -> Optional[List[Dict]]:
    """
    获取用户所有收藏的书籍列表（自动翻页）

    Args:
        token: 认证token
        delay: 请求间隔延迟（秒），避免请求过快

    Returns:
        包含所有书籍信息的列表，每个元素包含novelId, titleJp, titleZh, updateAt
    """
    all_books = []
    page = 0
    page_size = 30

    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {token}",
        "referer": "https://n.novelia.cc/favorite/web",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    while True:
        try:
            # 构建请求URL和参数
            params = {
                "page": page,
                "pageSize": page_size,
                "query": "",
                "provider": "kakuyomu,syosetu,novelup,hameln,pixiv,alphapolis",
                "type": 0,
                "level": 0,
                "translate": 0,
                "sort": "update"
            }

            print(f"正在请求Web第 {page + 1} 页...")

            response = requests.get(
                "https://n.novelia.cc/api/user/favored-web/default",
                params=params,
                headers=headers,
                timeout=30  # 设置超时时间
            )

            # 检查响应状态
            if response.status_code != 200:
                print(f"请求失败，状态码: {response.status_code}")
                break

            # 解析JSON响应
            data = response.json()

            # 检查是否有数据
            items = data.get("items", [])
            if not items:
                print("没有更多数据")
                break

            # 提取需要的字段
            for item in items:
                book_info = {
                    "novelId": item.get("novelId", ""),
                    "titleJp": item.get("titleJp", ""),
                    "titleZh": item.get("titleZh", ""),
                    "updateAt": item.get("updateAt", 0),
                    "providerId": item.get("providerId", "")  # 额外保留providerId用于标识来源
                }
                all_books.append(book_info)

            print(f"Web第 {page + 1} 页获取到 {len(items)} 条记录，总计 {len(all_books)} 条")

            # 如果返回的数据少于page_size，说明是最后一页
            if len(items) < page_size:
                print("已获取所有数据\n")
                break

            # 翻到下一页
            page += 1

            # 添加延迟，避免请求过快
            if delay > 0:
                time.sleep(delay)

        except requests.exceptions.Timeout:
            print(f"第 {page + 1} 页请求超时")
            break
        except requests.exceptions.RequestException as e:
            print(f"第 {page + 1} 页网络请求错误: {e}")
            break
        except ValueError as e:
            print(f"第 {page + 1} 页JSON解析错误: {e}")
            break
        except Exception as e:
            print(f"第 {page + 1} 页发生未知错误: {e}")
            break

    return all_books


def read_json(file_path: str, encoding: str = "utf-8") -> Optional[Any]:
    """
    读取JSON文件

    Args:
        file_path: JSON文件路径
        encoding: 文件编码，默认utf-8

    Returns:
        JSON数据，文件不存在或读取失败返回None
    """
    try:
        file_path = Path(file_path)

        # 检查文件是否存在
        if not file_path.exists():
            return None

        # 检查文件是否为空
        if file_path.stat().st_size == 0:
            return None

        # 读取并解析JSON
        with open(file_path, 'r', encoding=encoding) as f:
            return json.load(f)

    except Exception:
        return None


def write_json(data: Any, file_path: str, encoding: str = "utf-8", indent: int = 2, ensure_ascii: bool = False) -> bool:
    """
    写入JSON文件（覆盖写入，文件不存在则新建）

    Args:
        data: 要写入的数据
        file_path: 文件路径
        encoding: 文件编码，默认utf-8
        indent: JSON缩进，默认2个空格
        ensure_ascii: 是否确保ASCII，默认False（支持中文）

    Returns:
        成功返回True，失败返回False
    """
    try:
        file_path = Path(file_path)

        # 创建目录（如果不存在）
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        with open(file_path, 'w', encoding=encoding) as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)

        return True

    except Exception:
        return False


def build_message(web_updates: List[Dict], wenku_updates: List[Dict]) -> str:
    """
    构建通知消息内容

    Args:
        web_updates: 网络小说更新列表
        wenku_updates: 文库小说更新列表

    Returns:
        格式化的消息字符串
    """
    messages = []

    if web_updates:
        messages.append("网络小说更新：")
        for book in web_updates:
            # 时间戳转换为可读格式
            messages.append(
                f"- {book['titleZh']} (更新于: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(book['updateAt']))})")
    else:
        messages.append("网络小说无更新。")

    if wenku_updates:
        messages.append("\n文库小说更新：")
        for book in wenku_updates:
            messages.append(
                f"- {book['titleZh']} (更新于: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(book['updateAt']))})")
    else:
        messages.append("\n文库小说无更新。")

    return "\n".join(messages)


if __name__ == '__main__':
    config = YamlReader('config.yaml')

    jwt = login_to_novelia(config.get('novelia.username'), config.get('novelia.password'))
    if jwt is None:
        exit(1)

    print(f"登录成功")

    time.sleep(1)

    last_update = read_json('favorite_books.json')
    current_update = {"web": [], "wenku": []}

    # 处理收藏的网络小说
    web_update_books = []

    books = get_all_favorite_web_books(jwt, delay=0.5)
    if books is not None:
        if last_update is not None:
            last_web_books = last_update.get("web", [])
            # 比较更新
            last_web_dict = {book["novelId"]: book for book in last_web_books}
            for book in books:
                novel_id = book["novelId"]
                if novel_id in last_web_dict:
                    last_update_at = last_web_dict[novel_id]["updateAt"]
                    if book["updateAt"] > last_update_at:
                        web_update_books.append(book)

        # 保存到JSON文件
        current_update["web"] = books

    for web_update_book in web_update_books:
        print(f"更新的书籍: {web_update_book['titleZh']} (ID: {web_update_book['novelId']})")

    # 处理收藏的文库小说
    wenku_update_books = []

    books = get_all_favorite_wenku_books(jwt, delay=0.5)
    if books is not None:
        print(f"共获取到 {len(books)} 本收藏的文库书籍\n")

        if last_update is not None:
            last_wenku_books = last_update.get("wenku", [])
            # 比较更新
            last_wenku_dict = {book["novelId"]: book for book in last_wenku_books}
            for book in books:
                novel_id = book["novelId"]
                if novel_id in last_wenku_dict:
                    last_update_at = last_wenku_dict[novel_id]["updateAt"]
                    if book["updateAt"] > last_update_at:
                        wenku_update_books.append(book)

        # 保存到JSON文件
        current_update["wenku"] = books

    # 保存当前更新状态
    write_json(current_update, 'favorite_books.json')

    # 如果有更新则发送通知
    if web_update_books or wenku_update_books:
        send_notification(config.get("push"), "小说更新通知", build_message(web_update_books, wenku_update_books))
    else:
        print("没有小说更新，无需发送通知。")
