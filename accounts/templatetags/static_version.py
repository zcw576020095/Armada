import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(path):
    """在 static URL 后拼上文件 mtime 作为版本号，用于破除浏览器缓存。

    重建 output.css 后 mtime 变化 → URL 变化 → 浏览器强制重新下载，
    避免样式改了但用户看到的还是缓存里的旧 CSS。找不到文件时降级为普通 static。
    """
    url = static(path)
    abs_path = finders.find(path)
    if abs_path and os.path.exists(abs_path):
        return f'{url}?v={int(os.path.getmtime(abs_path))}'
    return url
