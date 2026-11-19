import ctypes
from ctypes import wintypes


class DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


CRYPTPROTECT_UI_FORBIDDEN = 0x1
DESCRIPTION = "Douyin Archiver Cookie"
SESSION_COOKIE_NAMES = {"sessionid", "sessionid_ss", "sid_guard"}


def _blob(data: bytes) -> tuple[DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    return (
        DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))),
        buffer,
    )


def protect_text(value: str) -> bytes:
    if not value:
        raise ValueError("Cookie 不能为空")
    source, source_buffer = _blob(value.encode("utf-8"))
    target = DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source),
        DESCRIPTION,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(target),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)
        del source_buffer


def unprotect_text(payload: bytes) -> str:
    source, source_buffer = _blob(payload)
    target = DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(target),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)
        del source_buffer


def cookie_field_names(value: str) -> set[str]:
    return {
        item.split("=", 1)[0].strip()
        for item in value.split(";")
        if "=" in item and item.split("=", 1)[0].strip()
    }


def validate_login_cookie(value: str) -> None:
    fields = cookie_field_names(value)
    if len(fields) < 3 or not fields.intersection(SESSION_COOKIE_NAMES):
        raise ValueError(
            "这不是完整的登录 Cookie。请复制 douyin.com 请求的整个 Cookie 请求头；"
            "单个 fg_uid、Token 或某一项 Cookie 无法代表登录态。"
        )

