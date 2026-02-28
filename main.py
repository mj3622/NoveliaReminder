import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, TypeVar, Tuple
from utils.MsgNotifier import send_notification
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.YamlReader import YamlReader

# 请求重试配置（可由 config 覆盖），用于应对 SSL/连接被对端关闭等不稳定情况
_retry_config = {"max_retries": 6, "backoff_sec": 5}

T = TypeVar("T")


def _retry_on_connection_error(
    request_func: Callable[[], T],
    max_retries: Optional[int] = None,
    backoff_sec: Optional[float] = None,
    context: str = "",
) -> T:
    """
    对网络请求进行重试，捕获 SSL/连接关闭等 RequestException，带退避等待。
    次数与间隔来自 config 的 request 段，未配置时使用 _retry_config 默认值。
    """
    n = max_retries if max_retries is not None else _retry_config["max_retries"]
    b = backoff_sec if backoff_sec is not None else _retry_config["backoff_sec"]
    last_exc = None
    for attempt in range(n):
        try:
            return request_func()
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt < n - 1:
                wait = b * (attempt + 1)
                msg = f"  请求失败 ({context}): {e}"
                print(f"{msg}\n  {wait} 秒后重试 ({attempt + 2}/{n})...")
                time.sleep(wait)
            else:
                raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("retry loop exited without return or raise")


def _session_with_retry() -> requests.Session:
    """创建带连接错误重试的 Session，减少连接复用导致的 SSL 关闭错误。"""
    session = requests.Session()
    total = _retry_config["max_retries"]
    retry = Retry(
        total=total,
        backoff_factor=min(2, _retry_config["backoff_sec"] / 2),
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=4)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def login_to_novelia(username: str, password: str, session: Optional[requests.Session] = None):
    url = "https://auth.novelia.cc/api/v1/auth/login"
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "referer": "https://auth.novelia.cc/",
    }
    data = {"app": "n", "username": username, "password": password}
    sess = session or requests

    try:
        response = _retry_on_connection_error(
            lambda: sess.post(url, headers=headers, json=data, timeout=30),
            context="登录",
        )
        if response.status_code != 200:
            print(f"登录失败，状态码: {response.status_code}，响应内容: {response.text}")
            return None
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"请求错误: {e}")
        return None


def get_all_favorite_wenku_books(
    token: str, delay: float = 0.5, session: Optional[requests.Session] = None
) -> Tuple[List[Dict], bool, int]:
    """
    获取用户所有收藏的文库书籍列表（自动翻页）

    Args:
        token: 认证token
        delay: 请求间隔延迟（秒），避免请求过快
        session: 可选，带重试的 Session，用于减轻 SSL/连接关闭错误

    Returns:
        (书籍列表, 列表请求是否曾因异常中断, 详情请求失败的本数)
    """
    all_books = []
    book_ids = []
    page = 0
    page_size = 24
    list_failed = False
    sess = session or requests

    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {token}",
        "referer": "https://n.novelia.cc/favorite/wenku/default?page=1&selected=1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    while True:
        try:
            params = {"page": page, "pageSize": page_size, "sort": "create"}
            print(f"\n正在请求文库第 {page + 1} 页...")

            response = _retry_on_connection_error(
                lambda: sess.get(
                    "https://n.novelia.cc/api/user/favored-wenku/default",
                    params=params,
                    headers=headers,
                    timeout=30,
                ),
                context=f"文库第 {page + 1} 页",
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
            list_failed = True
            break
        except requests.exceptions.RequestException as e:
            print(f"文库第 {page + 1} 页网络请求错误: {e}")
            list_failed = True
            break
        except ValueError as e:
            print(f"文库第 {page + 1} 页JSON解析错误: {e}")
            list_failed = True
            break
        except Exception as e:
            print(f"文库第 {page + 1} 页发生未知错误: {e}")
            list_failed = True
            break

    detail_fail_count = 0
    # 获取每本小说的详细信息（带重试，减轻 SSL 连接被关闭导致的失败）
    for i, novel_id in enumerate(book_ids):
        try:
            print(f"正在获取第 {i + 1}/{len(book_ids)} 本小说详情 (ID: {novel_id})...")
            headers["referer"] = f"https://n.novelia.cc/wenku/{novel_id}"
            url = f"https://n.novelia.cc/api/wenku/{novel_id}"

            response = _retry_on_connection_error(
                lambda u=url, h=dict(headers): sess.get(u, headers=h, timeout=30),
                context=f"小说详情 {novel_id}",
            )

            if response.status_code != 200:
                continue

            data = response.json()
            novel_info = {
                "novelId": novel_id,
                "titleJp": data.get("title", ""),
                "titleZh": data.get("titleZh", ""),
                "updateAt": data.get("latestPublishAt", 0),
            }
            all_books.append(novel_info)

        except requests.exceptions.RequestException as e:
            print(f"获取小说详情时发生错误 (ID: {novel_id}): {e}")
            detail_fail_count += 1
            continue

        # 添加延迟，避免请求过快
        if i < len(book_ids) - 1 and delay > 0:
            time.sleep(delay)

    return (all_books, list_failed, detail_fail_count)


def get_all_favorite_web_books(
    token: str, delay: float = 0.5, session: Optional[requests.Session] = None
) -> Tuple[List[Dict], bool]:
    """
    获取用户所有收藏的书籍列表（自动翻页）

    Args:
        token: 认证token
        delay: 请求间隔延迟（秒），避免请求过快
        session: 可选，带重试的 Session，用于减轻 SSL/连接关闭错误

    Returns:
        (书籍列表, 列表请求是否曾因异常中断)
    """
    all_books = []
    page = 0
    page_size = 30
    list_failed = False
    sess = session or requests

    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {token}",
        "referer": "https://n.novelia.cc/favorite/web",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    while True:
        try:
            params = {
                "page": page,
                "pageSize": page_size,
                "query": "",
                "provider": "kakuyomu,syosetu,novelup,hameln,pixiv,alphapolis",
                "type": 0,
                "level": 0,
                "translate": 0,
                "sort": "update",
            }
            print(f"正在请求Web第 {page + 1} 页...")

            response = _retry_on_connection_error(
                lambda: sess.get(
                    "https://n.novelia.cc/api/user/favored-web/default",
                    params=params,
                    headers=headers,
                    timeout=30,
                ),
                context=f"Web第 {page + 1} 页",
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
            list_failed = True
            break
        except requests.exceptions.RequestException as e:
            print(f"第 {page + 1} 页网络请求错误: {e}")
            list_failed = True
            break
        except ValueError as e:
            print(f"第 {page + 1} 页JSON解析错误: {e}")
            list_failed = True
            break
        except Exception as e:
            print(f"第 {page + 1} 页发生未知错误: {e}")
            list_failed = True
            break

    return (all_books, list_failed)


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
    if not config.get_all():
        print("未加载到有效配置，请检查 config.yaml 是否存在且格式正确。")
        exit(1)
    if not config.get('novelia.username') or not config.get('novelia.password'):
        print("请在 config.yaml 中配置 novelia.username 与 novelia.password。")
        exit(1)

    # 从配置读取请求重试与间隔（未配置则用默认值，保证服务器环境下更稳定）
    _retry_config["max_retries"] = int(config.get("request.retry_max_retries", 6))
    _retry_config["backoff_sec"] = float(config.get("request.retry_backoff_sec", 5))
    request_delay = float(config.get("request.delay_between_requests", 1.5))
    notify_on_final_failure = config.get("request.notify_on_final_failure", True)
    if isinstance(notify_on_final_failure, str):
        notify_on_final_failure = notify_on_final_failure not in ("false", "0", "no")

    session = _session_with_retry()

    jwt = login_to_novelia(
        config.get('novelia.username'),
        config.get('novelia.password'),
        session=session,
    )
    if jwt is None:
        if notify_on_final_failure and config.get("push"):
            send_notification(
                config.get("push"),
                "NoveliaReminder 登录失败",
                "登录轻小说机翻网失败（重试后仍失败），请检查账号与网络。",
                "error",
            )
        exit(1)

    print("登录成功")
    time.sleep(1)

    last_update = read_json('favorite_books.json')
    current_update = {"web": [], "wenku": []}
    final_failures = []  # 本次运行中“重试后仍失败”的项，用于最终告警

    # 处理收藏的网络小说
    web_update_books = []

    books, web_list_failed = get_all_favorite_web_books(jwt, delay=request_delay, session=session)
    if web_list_failed:
        final_failures.append("Web 收藏列表拉取曾因异常中断")
    current_update["web"] = books
    if books and last_update is not None:
        last_web_books = last_update.get("web", [])
        last_web_dict = {book["novelId"]: book for book in last_web_books}
        for book in books:
            novel_id = book["novelId"]
            if novel_id in last_web_dict:
                last_update_at = last_web_dict[novel_id]["updateAt"]
                if book["updateAt"] > last_update_at:
                    web_update_books.append(book)

    for web_update_book in web_update_books:
        print(f"更新的书籍: {web_update_book['titleZh']} (ID: {web_update_book['novelId']})")

    # 处理收藏的文库小说
    wenku_update_books = []

    books, wenku_list_failed, wenku_detail_fail_count = get_all_favorite_wenku_books(
        jwt, delay=request_delay, session=session
    )
    if wenku_list_failed:
        final_failures.append("文库收藏列表拉取曾因异常中断")
    if wenku_detail_fail_count > 0:
        final_failures.append(f"文库详情有 {wenku_detail_fail_count} 本在重试后仍获取失败")
    if books:
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

    # 存在“重试后仍失败”的项且开启告警时，发送失败告警（仅当推送配置存在时）
    if final_failures and notify_on_final_failure and config.get("push"):
        send_notification(
            config.get("push"),
            "NoveliaReminder 运行告警",
            "本次运行存在以下失败（重试后仍未成功）：\n\n" + "\n".join(f"- {m}" for m in final_failures),
            "error",
        )

    if not (web_update_books or wenku_update_books):
        print("没有小说更新，无需发送通知。")
