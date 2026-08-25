#!/usr/bin/env bash
# SQLite 每日备份（R1 准则：备份 API 方式，WAL 一致性快照）
# crontab 示例: 30 3 * * * /opt/houzhenwenyu/deploy/backup.sh
set -euo pipefail
DB=${1:-/opt/houzhenwenyu/server/app.db}
DEST=/opt/houzhenwenyu/backups
mkdir -p $DEST
STAMP=$(date +%Y%m%d_%H%M%S)
sqlite3 "$DB" "VACUUM INTO '$DEST/app_$STAMP.db'"
# 滚动保留 30 天
find $DEST -name "app_*.db" -mtime +30 -delete
echo "backup ok: app_$STAMP.db"
