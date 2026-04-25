# 升级报告

## 基本信息

| 项目 | 值 |
|------|-----|
| 仓库名 | django-easy-pdf |
| 升级时间 | 2026-03-13 |
| 升级状态 | ✅ 成功 |

## Python 版本

| 升级前 | 升级后 |
|--------|--------|
| >=2.7, >=3.4 | >=3.13 |

## 依赖变更

| 依赖 | 升级前 | 升级后 |
|------|--------|--------|
| django | >=1.8 | >=6.0.3 |
| xhtml2pdf | >=0.2b1 | >=0.2.17 |
| reportlab | >=3 | >=4.4.10 |
| html5lib | >=1.0b10 | >=1.1 |
| Pillow | >=2.4.0 | >=12.1.1 |
| pypdf | pyPdf2>=1.26 | pypdf>=6.8.0 |

## 代码修改

| 文件 | 修改类型 |
|------|----------|
| easy_pdf/rendering.py | Django API 迁移：urlquote → urllib.parse.quote |
| easy_pdf/rendering.py | Django API 迁移：django.utils.six.BytesIO → io.BytesIO |
| tests/urls.py | Django API 迁移：django.conf.urls.url → django.urls.re_path |
| tests/test_settings.py | 移除 django_nose 依赖（nose 使用已移除的 imp 模块） |

## 测试结果

| 测试类型 | 结果 |
|----------|------|
| 升级后 | ✅ 7 passed, 0 failed |

## 移除的依赖

- `httplib2` - xhtml2pdf 不再需要
- `pyPdf2` - 已被 pypdf 替代
- `django_nose` - nose 依赖已移除的 imp 模块，改用 Django 原生测试运行器

## 主要兼容性问题

1. **Django 6.0 API 变更**
   - `django.conf.urls.url` → `django.urls.re_path`
   - `django.utils.http.urlquote` → `urllib.parse.quote`
   - `django.utils.six.BytesIO` → `io.BytesIO`

2. **测试框架变更**
   - `django_nose` 依赖 `nose`，而 `nose` 使用了 Python 3.12 已移除的 `imp` 模块
   - 改用 Django 原生测试运行器

3. **依赖包名变更**
   - `pyPdf2` → `pypdf`（上游项目改名）

## 备注

所有测试通过，项目已成功升级到 Python 3.13 + Django 6.0 + 最新依赖。
