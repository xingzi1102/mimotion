# -*- coding: utf8 -*-
import math
import traceback
from datetime import datetime
import pytz
import uuid

import json
import random
import re
import time
import os

from util.aes_help import encrypt_data, decrypt_data
import util.zepp_helper as zeppHelper
import util.push_util as push_util


# ---------- 调度过滤：始终允许执行（因为实际执行时间会动态匹配最近计划小时） ----------
def should_run_now():
    """不再根据小时过滤，任何时间都允许，让步数函数自动匹配最近计划时间"""
    # 但仍可检查星期几？所有星期都有计划，所以直接返回 True
    return True


# ---------- 获取当天所有计划小时列表 ----------
def get_planned_hours(weekday):
    """根据星期几返回当天所有计划执行的小时（北京时间整点）"""
    # 周一至周四 (0-3)
    if weekday in (0, 1, 2, 3):
        return list(range(8, 22))   # 8,9,10,...,21
    # 周五 (4)
    elif weekday == 4:
        return [8] + list(range(12, 22))  # 8,12,13,...,21
    # 周六 (5)
    elif weekday == 5:
        return list(range(8, 22))
    # 周日 (6)
    elif weekday == 6:
        return list(range(8, 22))
    else:
        return []


# ---------- 步数范围生成函数（自动匹配最近计划小时） ----------
def get_min_max_by_time(hour=None, minute=None):
    """
    根据当前时间，找到当天计划小时中最接近的一个，然后计算该小时的步数范围。
    如果当前时间与多个计划小时距离相同，取较晚的那个（例如 8:00 距离 8:00 和 9:00 都是 0 和 1 小时，取 8:00）。
    """
    now = datetime.now(pytz.timezone('Asia/Shanghai'))
    weekday = now.weekday()
    current_time = now.replace(second=0, microsecond=0)  # 精确到分钟

    # 获取当天的计划小时列表
    planned_hours = get_planned_hours(weekday)
    if not planned_hours:
        # 理论上不会发生，但保险返回默认值
        return 3000, 3500

    # 构建每个计划小时对应的 datetime 对象（当天）
    base_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    planned_times = [base_date.replace(hour=h) for h in planned_hours]

    # 找出与当前时间最接近的计划时间（按绝对时间差，秒为单位）
    nearest_time = min(planned_times, key=lambda dt: abs((current_time - dt).total_seconds()))
    target_hour = nearest_time.hour

    # 线性插值辅助函数（与原始逻辑一致）
    def linear(start_h, start_min, start_max, end_h, end_min, end_max, hour):
        if hour < start_h:
            return start_min, start_max
        if hour >= end_h:
            return end_min, end_max
        ratio = (hour - start_h) / (end_h - start_h)
        min_step = int(start_min + (end_min - start_min) * ratio)
        max_step = int(start_max + (end_max - start_max) * ratio)
        return max(min_step, 500), max(max_step, min_step + 200)

    # 根据星期几和 target_hour 计算步数范围
    # 周一至周四
    if weekday in (0, 1, 2, 3):
        return linear(8, 3000, 3500, 21, 12000, 16000, target_hour)
    # 周五
    elif weekday == 4:
        if target_hour == 8:
            return 3000, 3500
        else:
            return linear(12, 3500, 4000, 21, 10000, 12000, target_hour)
    # 周六
    elif weekday == 5:
        return linear(8, 3000, 3500, 21, 19000, 21000, target_hour)
    # 周日
    elif weekday == 6:
        return linear(8, 2000, 3000, 21, 9000, 10000, target_hour)
    else:
        return 3000, 3500


# ---------- 以下是原始代码（未改动） ----------
# 获取默认值转int
def get_int_value_default(_config: dict, _key, default):
    _config.setdefault(_key, default)
    return int(_config.get(_key))


# 虚拟ip地址
def fake_ip():
    return f"{223}.{random.randint(64, 117)}.{random.randint(0, 255)}.{random.randint(0, 255)}"


# 账号脱敏
def desensitize_user_name(user):
    if len(user) <= 8:
        ln = max(math.floor(len(user) / 3), 1)
        return f'{user[:ln]}***{user[-ln:]}'
    return f'{user[:3]}****{user[-4:]}'


# 获取北京时间
def get_beijing_time():
    target_timezone = pytz.timezone('Asia/Shanghai')
    return datetime.now().astimezone(target_timezone)


# 格式化时间
def format_now():
    return get_beijing_time().strftime("%Y-%m-%d %H:%M:%S")


# 获取时间戳
def get_time():
    current_time = get_beijing_time()
    return "%.0f" % (current_time.timestamp() * 1000)


# 获取登录code
def get_access_token(location):
    code_pattern = re.compile("(?<=access=).*?(?=&)")
    result = code_pattern.findall(location)
    if result is None or len(result) == 0:
        return None
    return result[0]


def get_error_code(location):
    code_pattern = re.compile("(?<=error=).*?(?=&)")
    result = code_pattern.findall(location)
    if result is None or len(result) == 0:
        return None
    return result[0]


class MiMotionRunner:
    def __init__(self, _user, _passwd):
        self.user_id = None
        self.device_id = str(uuid.uuid4())
        user = str(_user)
        password = str(_passwd)
        self.invalid = False
        self.log_str = ""
        if user == '' or password == '':
            self.error = "用户名或密码填写有误！"
            self.invalid = True
            pass
        self.password = password
        if (user.startswith("+86")) or "@" in user:
            user = user
        else:
            user = "+86" + user
        if user.startswith("+86"):
            self.is_phone = True
        else:
            self.is_phone = False
        self.user = user

    # 登录
    def login(self):
        user_token_info = user_tokens.get(self.user)
        if user_token_info is not None:
            access_token = user_token_info.get("access_token")
            login_token = user_token_info.get("login_token")
            app_token = user_token_info.get("app_token")
            self.device_id = user_token_info.get("device_id")
            self.user_id = user_token_info.get("user_id")
            if self.device_id is None:
                self.device_id = str(uuid.uuid4())
                user_token_info["device_id"] = self.device_id
            ok, msg = zeppHelper.check_app_token(app_token)
            if ok:
                self.log_str += "使用加密保存的app_token\n"
                return app_token
            else:
                self.log_str += f"app_token失效 重新获取 last grant time: {user_token_info.get('app_token_time')}\n"
                app_token, msg = zeppHelper.grant_app_token(login_token)
                if app_token is None:
                    self.log_str += f"login_token 失效 重新获取 last grant time: {user_token_info.get('login_token_time')}\n"
                    login_token, app_token, user_id, msg = zeppHelper.grant_login_tokens(access_token, self.device_id,
                                                                                         self.is_phone)
                    if login_token is None:
                        self.log_str += f"access_token 已失效：{msg} last grant time:{user_token_info.get('access_token_time')}\n"
                    else:
                        user_token_info["login_token"] = login_token
                        user_token_info["app_token"] = app_token
                        user_token_info["user_id"] = user_id
                        user_token_info["login_token_time"] = get_time()
                        user_token_info["app_token_time"] = get_time()
                        self.user_id = user_id
                        return app_token
                else:
                    self.log_str += "重新获取app_token成功\n"
                    user_token_info["app_token"] = app_token
                    user_token_info["app_token_time"] = get_time()
                    return app_token

        # access_token 失效 或者没有保存加密数据
        access_token, msg = zeppHelper.login_access_token(self.user, self.password)
        if access_token is None:
            self.log_str += "登录获取accessToken失败：%s" % msg
            return None
        login_token, app_token, user_id, msg = zeppHelper.grant_login_tokens(access_token, self.device_id,
                                                                             self.is_phone)
        if login_token is None:
            self.log_str += f"登录提取的 access_token 无效：{msg}"
            return None

        user_token_info = dict()
        user_token_info["access_token"] = access_token
        user_token_info["login_token"] = login_token
        user_token_info["app_token"] = app_token
        user_token_info["user_id"] = user_id
        user_token_info["access_token_time"] = get_time()
        user_token_info["login_token_time"] = get_time()
        user_token_info["app_token_time"] = get_time()
        if self.device_id is None:
            self.device_id = uuid.uuid4()
        user_token_info["device_id"] = self.device_id
        user_tokens[self.user] = user_token_info
        return app_token

    # 主函数
    def login_and_post_step(self, min_step, max_step):
        if self.invalid:
            return "账号或密码配置有误", False
        app_token = self.login()
        if app_token is None:
            return "登陆失败！", False

        step = str(random.randint(min_step, max_step))
        self.log_str += f"已设置为随机步数范围({min_step}~{max_step}) 随机值:{step}\n"
        ok, msg = zeppHelper.post_fake_brand_data(step, app_token, self.user_id)
        return f"修改步数（{step}）[" + msg + "]", ok


def run_single_account(total, idx, user_mi, passwd_mi):
    idx_info = ""
    if idx is not None:
        idx_info = f"[{idx + 1}/{total}]"
    log_str = f"[{format_now()}]\n{idx_info}账号：{desensitize_user_name(user_mi)}\n"
    try:
        runner = MiMotionRunner(user_mi, passwd_mi)
        exec_msg, success = runner.login_and_post_step(min_step, max_step)
        log_str += runner.log_str
        log_str += f'{exec_msg}\n'
        exec_result = {"user": user_mi, "success": success,
                       "msg": exec_msg}
    except:
        log_str += f"执行异常:{traceback.format_exc()}\n"
        log_str += traceback.format_exc()
        exec_result = {"user": user_mi, "success": False,
                       "msg": f"执行异常:{traceback.format_exc()}"}
    print(log_str)
    return exec_result


def execute():
    # 不再限制时间，直接执行（should_run_now 始终 True）
    if not should_run_now():
        print(f"[{format_now()}] 今天没有执行计划，脚本退出")
        return

    user_list = users.split('#')
    passwd_list = passwords.split('#')
    exec_results = []
    if len(user_list) == len(passwd_list):
        idx, total = 0, len(user_list)
        if use_concurrent:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                exec_results = executor.map(lambda x: run_single_account(total, x[0], *x[1]),
                                            enumerate(zip(user_list, passwd_list)))
        else:
            for user_mi, passwd_mi in zip(user_list, passwd_list):
                exec_results.append(run_single_account(total, idx, user_mi, passwd_mi))
                idx += 1
                if idx < total:
                    time.sleep(sleep_seconds)
        if encrypt_support:
            persist_user_tokens()
        success_count = 0
        push_results = []
        for result in exec_results:
            push_results.append(result)
            if result['success'] is True:
                success_count += 1
        summary = f"\n执行账号总数{total}，成功：{success_count}，失败：{total - success_count}"
        print(summary)
        push_util.push_results(push_results, summary, push_config)
    else:
        print(f"账号数长度[{len(user_list)}]和密码数长度[{len(passwd_list)}]不匹配，跳过执行")
        exit(1)


def prepare_user_tokens() -> dict:
    data_path = r"encrypted_tokens.data"
    if os.path.exists(data_path):
        with open(data_path, 'rb') as f:
            data = f.read()
        try:
            decrypted_data = decrypt_data(data, aes_key, None)
            return json.loads(decrypted_data.decode('utf-8', errors='strict'))
        except:
            print("密钥不正确或者加密内容损坏 放弃token")
            return dict()
    else:
        return dict()


def persist_user_tokens():
    data_path = r"encrypted_tokens.data"
    origin_str = json.dumps(user_tokens, ensure_ascii=False)
    cipher_data = encrypt_data(origin_str.encode("utf-8"), aes_key, None)
    with open(data_path, 'wb') as f:
        f.write(cipher_data)
        f.flush()
        f.close()


if __name__ == "__main__":
    # 北京时间
    time_bj = get_beijing_time()
    encrypt_support = False
    user_tokens = dict()
    if os.environ.__contains__("AES_KEY") is True:
        aes_key = os.environ.get("AES_KEY")
        if aes_key is not None:
            aes_key = aes_key.encode('utf-8')
            if len(aes_key) == 16:
                encrypt_support = True
        if encrypt_support:
            user_tokens = prepare_user_tokens()
        else:
            print("AES_KEY未设置或者无效 无法使用加密保存功能")
    if os.environ.__contains__("CONFIG") is False:
        print("未配置CONFIG变量，无法执行")
        exit(1)
    else:
        config = dict()
        try:
            config = dict(json.loads(os.environ.get("CONFIG")))
        except:
            print("CONFIG格式不正确，请检查Secret配置，请严格按照JSON格式：使用双引号包裹字段和值，逗号不能多也不能少")
            traceback.print_exc()
            exit(1)

        push_config = push_util.PushConfig(
            push_plus_token=config.get('PUSH_PLUS_TOKEN'),
            push_plus_hour=config.get('PUSH_PLUS_HOUR'),
            push_plus_max=get_int_value_default(config, 'PUSH_PLUS_MAX', 30),
            push_wechat_webhook_key=config.get('PUSH_WECHAT_WEBHOOK_KEY'),
            telegram_bot_token=config.get('TELEGRAM_BOT_TOKEN'),
            telegram_chat_id=config.get('TELEGRAM_CHAT_ID')
        )
        sleep_seconds = config.get('SLEEP_GAP')
        if sleep_seconds is None or sleep_seconds == '':
            sleep_seconds = 5
        sleep_seconds = float(sleep_seconds)
        users = config.get('USER')
        passwords = config.get('PWD')
        if users is None or passwords is None:
            print("未正确配置账号密码，无法执行")
            exit(1)

        # 获取步数范围（自动匹配最近计划时间）
        min_step, max_step = get_min_max_by_time()

        use_concurrent = config.get('USE_CONCURRENT')
        if use_concurrent is not None and use_concurrent == 'True':
            use_concurrent = True
        else:
            print(f"多账号执行间隔：{sleep_seconds}")
            use_concurrent = False

        execute()
