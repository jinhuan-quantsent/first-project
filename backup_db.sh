#!/bin/bash
# MySQL自动备份脚本
# 每天03:00执行，保留最近7天

BACKUP_DIR="/opt/fund-sentiment/backups"
DB_USER="funduser"
DB_PASS="FundSent2026!"
DB_NAME="fund_sentiment"
DATE=$(date +%Y-%m-%d)
BACKUP_FILE="$BACKUP_DIR/fund_sentiment_$DATE.sql.gz"
RETENTION_DAYS=7

# 创建备份目录
mkdir -p $BACKUP_DIR

# 执行备份
echo "[$(date)] 开始备份 $DB_NAME ..."
mysqldump -u $DB_USER -p"$DB_PASS" --single-transaction --routines --triggers $DB_NAME 2>/dev/null | gzip > $BACKUP_FILE

if [ $? -eq 0 ]; then
    SIZE=$(du -h $BACKUP_FILE | cut -f1)
    echo "[$(date)] 备份成功: $BACKUP_FILE ($SIZE)"
    
    # 清理7天前的备份
    find $BACKUP_DIR -name "fund_sentiment_*.sql.gz" -mtime +$RETENTION_DAYS -delete
    echo "[$(date)] 已清理 ${RETENTION_DAYS}天前的旧备份"
    
    # 列出当前备份
    echo "[$(date)] 当前备份列表:"
    ls -lh $BACKUP_DIR/fund_sentiment_*.sql.gz 2>/dev/null
else
    echo "[$(date)] 备份失败!"
fi
