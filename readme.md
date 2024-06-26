# FFDraw: 一个针对FFxiv的悬浮窗图形显示框架

### python 版本(建议)

* 需求 `python3.11` 的 `x64版本`作为运行环境
* 下载专案后在专案目录运行 `python -m pip install -r requirements.txt` 安装依赖
* 建议使用`venv` 或 `virtualenv` 等虚拟环境以隔离依赖
* 如果遇到安装依赖问题请自行搜索 `pip换源` 相关
* 执行 `main.py`

### 注

* 专为遇到图层黑色无法穿透之类修改
* 隐藏了原绘制窗口，故需要使用IGD插件进行注入绘制
* 已在IGD插件中取消使用VFX绘制


