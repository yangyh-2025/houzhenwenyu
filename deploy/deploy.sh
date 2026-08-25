#!/usr/bin/env bash
# 候诊闻语 标准化部署脚本（目标：空白 Ubuntu 22.04/Debian 12）
# 用法: 以 root 在仓库根目录执行  bash deploy/deploy.sh
set -euo pipefail

APP_DIR=/opt/houzhenwenyu
REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)

echo "== 1. 系统依赖 =="
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip nginx >/dev/null
id -u hwyapp >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin hwyapp

echo "== 2. 目录与代码 =="
mkdir -p $APP_DIR
rsync -a --delete --exclude '.git' --exclude 'node_modules' \
      --exclude '*.db' --exclude '.env' --exclude 'web/src' --exclude 'docs' \
      "$REPO_DIR/server/" "$APP_DIR/server/"
mkdir -p $APP_DIR/web
rsync -a --delete "$REPO_DIR/web/dist/" "$APP_DIR/web/dist/"

echo "== 3. Python 虚拟环境 =="
python3 -m venv $APP_DIR/venv
$APP_DIR/venv/bin/pip install --quiet -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r $APP_DIR/server/requirements.txt

echo "== 4. 配置 =="
if [ ! -f $APP_DIR/.env ]; then
    cp deploy/.env.example $APP_DIR/.env
    echo ">>> 已生成 $APP_DIR/.env —— 请立即编辑：改 SECRET_KEY、DOCTOR_PASSWORD、AI_PROVIDER=mimo 与 AI_API_KEY！"
fi
chown -R hwyapp:hwyapp $APP_DIR

echo "== 5. systemd + nginx =="
cp deploy/houzhenwenyu.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now houzhenwenyu
cp deploy/nginx.conf.sample /etc/nginx/sites-available/houzhenwenyu.conf
ln -sf /etc/nginx/sites-available/houzhenwenyu.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "== 6. 验证 =="
sleep 2
curl -fsS http://127.0.0.1:8000/api/health && echo " <- 后端 OK"
echo "部署完成。下一步：配置域名证书后浏览器访问 https://<域名>/"
