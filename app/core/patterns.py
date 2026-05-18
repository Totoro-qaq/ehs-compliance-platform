"""集中定义校验用正则（字符串供 Pydantic Field(pattern=)；编译版供运行时）。"""

from __future__ import annotations

import re

# 公司名称校验用 Python re（Pydantic 内置正则为 Rust 引擎，部分 Unicode 类会触发限制）
ORG_NAME_RE = re.compile(r'^[\w\u4e00-\u9fff\s·.&（）()\-—]{1,255}$')


def validate_organization_name(value: str) -> str:
    s = value.strip()
    if not ORG_NAME_RE.fullmatch(s):
        raise ValueError('公司名称长度或字符不合法（允许中英文、数字、部分标点）')
    return s


# 登录用户名（ASCII，供 Pydantic pattern）
USERNAME: str = r'^[a-zA-Z0-9_.-]{3,64}$'

# 密码复杂度在 Pydantic 中用 validator 实现（Rust 正则不支持先行断言）
PASSWORD_HINT: str = '8-128 位非空白，须含小写、大写、数字'


# UUID（不区分大小写）
UUID_HEX: str = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

_UUID_HEX_RE = re.compile(UUID_HEX)


def is_uuid(value: str) -> bool:
    return bool(_UUID_HEX_RE.fullmatch(value.strip()))


# 注册用手机号：存库前规范为 11 位数字（含可选 +86 / 86 前缀）
_CN_MOBILE_RE = re.compile(r'^1[3-9]\d{9}$')


def normalize_cn_mobile(value: str) -> str:
    s = re.sub(r'[\s-]', '', value.strip())
    if s.startswith('+86'):
        s = s[3:]
    elif s.startswith('86') and len(s) == 13:
        s = s[2:]
    if not _CN_MOBILE_RE.fullmatch(s):
        raise ValueError('请输入合法的中国大陆手机号（11 位，1 开头）')
    return s
