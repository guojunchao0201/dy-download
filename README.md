# 抖音主页归档器

这是一个只在本机运行的抖音主页下载管理器，下载能力由同目录下的
[`f2`](https://github.com/Johnserf-Seed/f2) 提供。

推荐使用 Windows x64 与 Python 3.11 以上版本。当前安装脚本默认使用
`D:\devtools\python314-x64\python.exe`。

## 获取源码

项目使用 `f2` Git 子模块：

```powershell
git clone --recurse-submodules https://github.com/guojunchao0201/dy-download.git
cd dy-download
```

其中 `--recurse-submodules` 表示：克隆主项目时，同时初始化并下载项目引用的
Git 子模块。本项目没有把 `f2` 的源码复制到当前仓库，而是记录了对
[`Johnserf-Seed/f2`](https://github.com/Johnserf-Seed/f2) 指定版本的引用。

上面的命令等价于：

```powershell
git clone https://github.com/guojunchao0201/dy-download.git
cd dy-download
git submodule update --init --recursive
```

如果只执行普通的 `git clone`，`f2` 目录不会包含可用源码，首次安装将无法正常完成。

如果已经普通克隆，可补充执行：

```powershell
git submodule update --init --recursive
```

## 数据位置

虚拟环境、依赖缓存、临时文件、登录信息和下载内容默认全部位于本项目的 D 盘目录：

- `.venv/`：Python 虚拟环境
- `.cache/pip/`：pip 缓存
- `.tmp/`：安装与运行临时文件
- `data/`：加密 Cookie、任务数据库和日志
- `downloads/`：视频文件

Cookie 使用当前 Windows 用户的 DPAPI 加密，不能在其他账号或电脑上解密。

## 启动

Windows 用户可以直接双击项目根目录下的：

```text
启动抖音下载器.cmd
```

脚本会检查服务和虚拟环境，必要时完成首次安装，然后启动服务并自动打开浏览器。
控制台窗口需要保持打开；按 `Ctrl+C` 或关闭窗口即可停止服务。

也可以使用下面的 PowerShell 命令手动安装和启动。

首次安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

启动服务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

然后打开 <http://127.0.0.1:8765>。

安装脚本优先使用清华 PyPI 镜像，失败后才使用 PyPI 官方源。GitHub 仓库仍直接从
GitHub 官方源获取。

