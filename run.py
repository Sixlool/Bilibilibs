# -*- coding: utf-8 -*-
"""
系统启动入口
开发：python run.py
生产：gunicorn -w 4 -b 0.0.0.0:8000 run:app（见 Dockerfile / deploy/gunicorn.conf.py）
"""

import config
from app import create_app

app = create_app()

if __name__ == "__main__":
    # debug 由 config.DEBUG 控制：development 开、production 关
    app.run(host="0.0.0.0", port=5000, debug=config.DEBUG)
